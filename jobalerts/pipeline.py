"""fetch → dedup → relevance → description → citizenship → outbox (research §9, §11, §13; PLAN §3–4)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from . import citizenship
from .config import Settings
from .connectors import Connector
from .connectors import ashby as ashby_mod
from .connectors import greenhouse as gh_mod
from .connectors import lever as lever_mod
from .db import Store, dumps, now
from .http import FetchError, Http
from .models import Decision, NormalizedJob
from .employment import contract_or_hourly
from .normalize import ats_identity, company_key, extract_season, fingerprint, normalize_url, strip_html
from .relevance import classify
from .years import required_years

log = logging.getLogger(__name__)

# Apply-URL preference when one job is seen by several sources: a direct ATS connector (3) beats a list that links
# to the ATS (2) beats the Simplify redirect (1).
SOURCE_RANK = {"simplify": 1, "markdown": 2, "getro": 2, "consider": 2}
SHORT_LINK_HOSTS = {"go.vansh.nyc"}
MAX_DESCRIPTIONS_PER_RUN = 80
MAX_SHORT_LINKS_PER_RUN = 500          # one redirect each, no body: cheap
DEGRADED_AFTER, BROKEN_AFTER, CIRCUIT_HOURS = 3, 6, 6


@dataclass
class RunStats:
    source: str
    status: str
    fetched: int = 0
    new_jobs: int = 0
    new_relevant: int = 0
    error: str | None = None


def idem_key(*parts: object) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


class Pipeline:
    def __init__(self, settings: Settings, store: Store, http: Http):
        self.s = settings
        self.db = store
        self.http = http
        self._ashby_cache: dict[str, dict[str, str]] = {}
        self._by_key = {c.key: c for c in settings.connectors}
        # company_key(name) → (id, tier) so aggregator rows for tracked companies (feed-only ones too) get their tier
        self._alias = {company_key(c.company): (c.company_id, c.tier) for c in settings.connectors if c.company_id}
        self._alias.update(settings.directory)

    # ── one source, end to end ───────────────────────────────────────────
    async def run_source(self, conn: Connector) -> RunStats:
        src = self.db.source(conn.key, conn.kind, conn.company)
        if src["circuit_open_until"] and src["circuit_open_until"] > now():
            return RunStats(conn.key, "skipped")
        run_id = self.db.exec("INSERT INTO runs(source, started_at) VALUES (?,?)", conn.key, now()).lastrowid
        try:
            res = await conn.fetch(self.http, src["etag"])
            if res.jobs is None:
                stats = RunStats(conn.key, "not_modified")
            else:
                stats = await self._process(conn, res.jobs, seeded=bool(src["seeded"]))
            self.db.exec(
                "UPDATE sources SET etag=?, seeded=1, last_run_at=?, last_success_at=?, consecutive_failures=0,"
                " circuit_open_until=NULL, last_error=NULL, last_fetched=COALESCE(?, last_fetched) WHERE key=?",
                res.etag, now(), now(), stats.fetched if res.jobs is not None else None, conn.key)
        except Exception as e:  # noqa: BLE001 — one broken source must never stop the others
            err = f"{type(e).__name__}: {e}"[:500]
            log.warning("source %s failed: %s", conn.key, err)
            stats = RunStats(conn.key, "failed", error=err)
            self._record_failure(conn, err)
        self.db.exec("UPDATE runs SET finished_at=?, status=?, fetched=?, new_jobs=?, new_relevant=?, error=? WHERE id=?",
                     now(), stats.status, stats.fetched, stats.new_jobs, stats.new_relevant, stats.error, run_id)
        return stats

    def _record_failure(self, conn: Connector, err: str) -> None:
        self.db.exec("UPDATE sources SET consecutive_failures=consecutive_failures+1, last_run_at=?, last_error=?"
                     " WHERE key=?", now(), err, conn.key)
        fails = self.db.one("SELECT consecutive_failures FROM sources WHERE key=?", conn.key)[0]
        if fails >= BROKEN_AFTER:
            until = (datetime.now(timezone.utc) + timedelta(hours=CIRCUIT_HOURS)).isoformat(timespec="seconds")
            self.db.exec("UPDATE sources SET circuit_open_until=? WHERE key=?", until, conn.key)
            self._ops_alert(f"broken:{conn.key}:{now()[:10]}",
                            f"🔴 Source **{conn.key}** ({conn.company}) failed {fails}× in a row; paused {CIRCUIT_HOURS}h.\n`{err}`")
        elif fails == DEGRADED_AFTER:
            self._ops_alert(f"degraded:{conn.key}:{now()[:10]}",
                            f"🟠 Source **{conn.key}** ({conn.company}) failed {fails}× in a row.\n`{err}`")

    def _ops_alert(self, key: str, text: str) -> None:
        self.db.exec("INSERT INTO alerts(alert_type, channel, idempotency_key, payload, created_at)"
                     " VALUES ('ops','ops',?,?,?) ON CONFLICT(idempotency_key) DO NOTHING",
                     idem_key(key), dumps({"content": text}), now())

    # ── the three phases ─────────────────────────────────────────────────
    async def _process(self, conn: Connector, jobs: list[NormalizedJob], seeded: bool) -> RunStats:
        stats = RunStats(conn.key, "ok", fetched=len(jobs))
        horizon = datetime.now(timezone.utc) - timedelta(hours=int(self.s.alerts.get("bootstrap_alert_hours", 48)))

        # Phase 1: match known jobs; classify unknown ones; park the relevant ones.
        pending: list[tuple[NormalizedJob, Decision]] = []
        with self.db.tx():
            for job in jobs:
                self._attach_company(job)
                if (cid := self._resolve(job)) is not None:
                    self._touch(cid, job)
                    continue
                d = classify(job, self.s.relevance)
                if d.accept and not seeded and not (job.posted_at and job.posted_at >= horizon):
                    d = Decision(True, "seeded (existed before first poll)", d.level, d.category, d.flags)
                    self._create(job, d, alert=False)
                    stats.new_jobs += 1
                elif d.accept:
                    pending.append((job, d))
                else:
                    self._create(job, d, alert=False)
                    stats.new_jobs += 1

        # Phase 2: real URLs for short links, then descriptions, only for the few survivors (network, outside the
        # transaction). A resolved URL lets phase 3 find the job under the URL another source already saw it by.
        await self._resolve_short_links([j for j, _ in pending])
        await self._enrich([j for j, _ in pending])

        # Phase 3: citizenship check, then canonical row + outbox row in one transaction.
        with self.db.tx():
            for job, d in pending:
                if (cid := self._resolve(job)) is not None:   # a sibling in this batch got there first
                    self._touch(cid, job)
                    continue
                cz = citizenship.check(job.description, job.sponsorship,
                                       (job.company_id or "") in self.s.likely_citizenship, job.title)
                elig = self.s.eligibility
                if cz.status == "reject" and elig.get("citizenship_filter", True):
                    d = Decision(False, "requires US citizenship/clearance", d.level, d.category, d.flags)
                elif cz.no_sponsorship and elig.get("drop_no_sponsorship", False):
                    d = Decision(False, "no visa sponsorship", d.level, d.category, d.flags)
                elif reason := self._description_filters(job, d):
                    d = Decision(False, reason, d.level, d.category, d.flags)
                self._create(job, d, alert=d.accept, cz=cz)
                stats.new_jobs += 1
                stats.new_relevant += int(d.accept)
        return stats

    def _attach_company(self, job: NormalizedJob) -> None:
        if job.company_id is None and (hit := self._alias.get(company_key(job.company))):
            job.company_id, job.tier = hit

    def _description_filters(self, job: NormalizedJob, d: Decision) -> str | None:
        """Rules that need the description (ported from jobhunter): years of experience for non-intern roles, and
        contract / hourly roles. Returns a drop reason, or None to keep the job (possibly with a flag added)."""
        f = self.s.filters
        max_years = f.get("max_years_required", 2)
        if max_years is not None and d.level != "intern" and job.description:
            years = required_years(f"{job.title}\n{job.description}", company=job.company)
            if years is not None and years > int(max_years):
                # Multi-level postings ("Associate 0-2 yrs / Mid 3-5 yrs") and "Master's + 1 yr OR Bachelor's + 3 yrs"
                # read as the higher number, so by default this only warns.
                if f.get("years_action", "flag") == "drop":
                    return f"requires {years}+ years of experience (max {max_years})"
                d.flags.append(f"asks for {years}+ years of experience")
        exclude = set(f.get("employment_exclude", ["contract", "hourly"]) or [])
        if exclude:
            return contract_or_hourly(job.title, job.description, exclude, f.get("contract_to_hire", "keep"),
                                      f.get("hourly_internships", "keep"))
        return None

    # ── dedup cascade L0–L3 ──────────────────────────────────────────────
    def _resolve(self, job: NormalizedJob) -> int | None:
        if r := self.db.one("SELECT canonical_job_id FROM job_sources WHERE source=? AND source_job_id=?",
                            job.source, job.source_job_id):
            return r[0]
        if r := self.db.one("SELECT id FROM canonical_jobs WHERE normalized_url=?", normalize_url(job.url)):
            return r[0]
        # ATS ids are globally unique within an ATS (numeric ids, UUIDs, JR numbers), and the org label
        # differs between URL forms (job-boards.greenhouse.io/instacart vs instacart.careers/?gh_jid=)
        ident = ats_identity(job.url)
        if ident and (r := self.db.one("SELECT id FROM canonical_jobs WHERE ats=? AND ats_id=?", ident[0], ident[2])):
            return r[0]
        fp = self._fp(job)
        for r in self.db.all("SELECT id, ats, ats_id FROM canonical_jobs WHERE fingerprint=?", fp):
            if not (ident and r["ats"] == ident[0] and r["ats_id"] and r["ats_id"] != ident[2]):
                return r["id"]   # never merge two distinct requisitions from the same ATS
        return None

    def _fp(self, job: NormalizedJob) -> str:
        season = extract_season(job.title) or next((t for t in job.terms if t != "N/A"), None)
        return fingerprint(job.company, job.title, job.locations, season)

    def _touch(self, cid: int, job: NormalizedJob) -> None:
        t = now()
        self.db.exec("INSERT INTO job_sources(canonical_job_id, source, source_job_id, url, first_seen_at, last_seen_at)"
                     " VALUES (?,?,?,?,?,?) ON CONFLICT(source, source_job_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
                     cid, job.source, job.source_job_id, job.url, t, t)
        rank = SOURCE_RANK.get(job.source.split(":")[0], 3)
        self.db.exec("UPDATE canonical_jobs SET last_seen_at=?,"
                     " apply_url=CASE WHEN ?>apply_url_rank THEN ? ELSE apply_url END,"
                     " apply_url_rank=MAX(apply_url_rank, ?) WHERE id=?", t, rank, job.url, rank, cid)

    def _create(self, job: NormalizedJob, d: Decision, alert: bool,
                cz: citizenship.CitizenshipResult | None = None) -> int:
        t = now()
        ident = ats_identity(job.url) or (None, None, None)
        snippet = _snippet(job.description)
        cid = self.db.exec(
            "INSERT INTO canonical_jobs(company, company_id, tier, title, apply_url, apply_url_rank, normalized_url,"
            " ats, ats_org, ats_id, fingerprint, locations, terms, posted_at, first_seen_at, last_seen_at, relevant,"
            " reason, level, category, flags, citizenship, citizenship_evidence, no_sponsorship, description_snippet,"
            " description, compensation) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            job.company, job.company_id, job.tier, job.title, job.url, SOURCE_RANK.get(job.source.split(":")[0], 3),
            normalize_url(job.url), *ident, self._fp(job), dumps(job.locations), dumps(job.terms),
            job.posted_at.isoformat() if job.posted_at else None, t, t, int(d.accept), d.reason, d.level, d.category,
            dumps(d.flags), cz.status if cz else None, cz.evidence if cz else None,
            int(cz.no_sponsorship) if cz else None, snippet,
            (job.description[:40000] if d.accept and job.description else None), job.compensation,
        ).lastrowid
        self._touch(cid, job)
        if alert:
            route = self.s.route_for(job.tier, d.level)
            self.db.exec("INSERT INTO alerts(canonical_job_id, alert_type, channel, idempotency_key, created_at)"
                         " VALUES (?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING",
                         cid, "new", route, idem_key(cid, "new", "discord", "v1"), t)
        return cid

    # ── short links ──────────────────────────────────────────────────────
    async def _resolve_short_links(self, jobs: list[NormalizedJob]) -> None:
        async def one(job: NormalizedJob) -> None:
            try:
                job.url = await self.http.resolve(job.url)
            except FetchError as e:
                log.info("could not resolve %s: %s", job.url, e)
        todo = [j for j in jobs if urlsplit(j.url).netloc.lower() in SHORT_LINK_HOSTS][:MAX_SHORT_LINKS_PER_RUN]
        await asyncio.gather(*(one(j) for j in todo))

    # ── descriptions ─────────────────────────────────────────────────────
    async def _enrich(self, jobs: list[NormalizedJob]) -> None:
        todo = [j for j in jobs if not j.description][:MAX_DESCRIPTIONS_PER_RUN]
        await asyncio.gather(*(self._describe(j) for j in todo))

    async def _describe(self, job: NormalizedJob) -> None:
        try:
            conn = self._by_key.get(job.source)
            if conn is not None and hasattr(conn, "fetch_description"):
                job.description = await conn.fetch_description(self.http, job)   # type: ignore[attr-defined]
                return
            ident = ats_identity(job.url)
            if not ident:
                return
            ats, org, jid = ident
            if ats == "greenhouse":
                # Custom-domain boards (careers.withwaymo.com/?gh_jid=…): the URL host is not the board slug.
                if conn is not None and conn.kind == "greenhouse":
                    org = conn.slug
                elif "." in org:
                    return
                job.description = await gh_mod.fetch_description(self.http, org, jid)
            elif ats == "lever":
                job.description = await lever_mod.fetch_description(self.http, org, jid)
            elif ats == "ashby":
                if org not in self._ashby_cache:
                    self._ashby_cache[org] = await ashby_mod.fetch_board_descriptions(self.http, org)
                job.description = self._ashby_cache[org].get(jid) or None
            elif ats == "workday":
                job.description = await _workday_description(self.http, job.url)
        except (FetchError, KeyError, ValueError, TypeError) as e:
            log.info("no description for %s: %s", job.url, e)


async def _workday_description(http: Http, url: str) -> str | None:
    m = re.match(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)(/job/.+)", url)
    if not m:
        return None
    tenant, wd, site, path = m.groups()
    r = await http.get(f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}", retries=1)
    return strip_html(((r.data or {}).get("jobPostingInfo") or {}).get("jobDescription"))


def _snippet(desc: str | None, n: int = 320) -> str | None:
    if not desc:
        return None
    text = re.sub(r"\s+", " ", desc).strip()
    return text[:n].rsplit(" ", 1)[0] + "…" if len(text) > n else text
