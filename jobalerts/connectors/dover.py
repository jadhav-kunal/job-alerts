"""Dover's public job-board feed: every company hiring through Dover (~500 open jobs, mostly startups), read from
Dover's own JSON API. Endpoints from jobhunter's boards/dover.py (MIT).

The feed has no descriptions; fetch_description reads one posting for each job that passes the title rules.
"""
from __future__ import annotations

from urllib.parse import quote

from ..http import Http
from ..models import NormalizedJob
from ..normalize import strip_html
from . import Connector, FetchResult, parse_iso

API = "https://app.dover.com/api/v1"
FEED_URL = API + "/job-board/jobs/"           # the one Dover path that keeps its trailing slash
POSTING_URL = API + "/inbound/application-portal-job/{job_id}"
PAGE_SIZE, MAX_PAGES = 100, 20


def apply_url(company: str, job_id: str) -> str:
    return f"https://app.dover.com/apply/{quote(company or 'company', safe='')}/{job_id}"


class DoverConnector(Connector):
    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        raw, offset = [], 0
        for _ in range(MAX_PAGES):
            r = await http.get(FEED_URL, params={"limit": PAGE_SIZE, "offset": offset})
            page = [j for j in (r.data or {}).get("results") or [] if isinstance(j, dict) and j.get("id")]
            raw += page
            if not (r.data or {}).get("next") or not page:
                break
            offset += len(page)
        jobs = []
        for j in raw:
            company = str((j.get("client") or {}).get("name") or "").strip() or "Unknown"
            jid = str(j["id"]).lower()
            locs = [str(loc.get("name")) for loc in j.get("locations") or [] if isinstance(loc, dict) and loc.get("name")]
            if j.get("workplace_type") == "REMOTE" and not any("remote" in x.lower() for x in locs):
                locs = [f"Remote - {x}" for x in locs] or ["Remote"]
            job = self.job(
                source_job_id=jid,
                title=str(j.get("title") or "").strip(),
                url=apply_url(company, jid),
                locations=locs,
                posted_at=parse_iso(j.get("date_posted")),
                employment_type=j.get("employment_type"),
                compensation=_comp(j.get("compensation")),
                raw={"id": jid, "client": (j.get("client") or {}).get("slug")},
            )
            job.company, job.company_id, job.tier = company, None, None
            jobs.append(job)
        return FetchResult(jobs)

    async def fetch_description(self, http: Http, job: NormalizedJob) -> str | None:
        r = await http.get(POSTING_URL.format(job_id=quote(job.source_job_id, safe="")), retries=1)
        return strip_html((r.data or {}).get("user_provided_description")) or None


def _comp(c: dict | None) -> str | None:
    if not c or not c.get("lower_bound") or not c.get("open_to_sharing_comp", True):
        return None
    lo, hi = c["lower_bound"], c.get("upper_bound") or c["lower_bound"]
    per = {"YEARLY": "/yr", "HOURLY": "/hr"}.get(str(c.get("salary_range_type")), "")
    cur = "$" if c.get("currency_code", "USD") == "USD" else f"{c.get('currency_code')} "
    fmt = (lambda v: f"{cur}{v / 1000:.0f}K") if per == "/yr" else (lambda v: f"{cur}{v:g}")
    return f"{fmt(lo)} – {fmt(hi)}{per}" if hi != lo else f"{fmt(lo)}{per}"
