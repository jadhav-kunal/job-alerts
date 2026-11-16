"""Loads config/preferences.yaml, config/companies.yaml and .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .connectors import Connector, registry
from .normalize import company_key
from .relevance import RelevancePrefs

ROOT = Path(__file__).resolve().parent.parent
MULTIPLIER = {"peak": 1, "normal": 2, "quiet": 4}
SLOW_KINDS = {"workday", "amazon", "eightfold"}
TIERS = ("big_tech", "tier1", "tier2", "tier3")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


@dataclass
class Settings:
    raw: dict[str, Any]
    relevance: RelevancePrefs
    connectors: list[Connector]
    intervals: dict[str, int]                      # connector key → seconds
    likely_citizenship: set[str] = field(default_factory=set)
    # company_key(name or alias) → (company id, tier), for every company in companies.yaml, including the
    # feed-only ones (Meta, Google, …), so aggregator rows get their tier and land in the right channel.
    directory: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def filters(self) -> dict[str, Any]:
        return self.raw.get("filters", {})

    def route_for(self, tier: str | None, level: str | None) -> str:
        """Outbox channel for a job alert: its tier (big_tech / tier1 / … / other) or its level (intern / new_grad)."""
        if self.alerts.get("route_by", "tier") == "tier":
            return tier if tier in TIERS else "other"
        return "intern" if level == "intern" else "new_grad"

    @property
    def alerts(self) -> dict[str, Any]:
        return self.raw.get("alerts", {})

    @property
    def eligibility(self) -> dict[str, Any]:
        return self.raw.get("eligibility", {})

    def webhook_for(self, route: str) -> str | None:
        var = self.alerts.get("routes", {}).get(route)
        return (os.environ.get(var) if var else None) or os.environ.get("DISCORD_WEBHOOK_URL")

    @property
    def bot_token(self) -> str | None:
        return os.environ.get("DISCORD_BOT_TOKEN") or None

    def channel_for(self, route: str) -> str | None:
        """Bot mode: DISCORD_WEBHOOK_INTERNSHIPS → DISCORD_CHANNEL_INTERNSHIPS, falling back to DISCORD_CHANNEL_ID."""
        var = self.alerts.get("routes", {}).get(route)
        var = var.replace("WEBHOOK", "CHANNEL") if var else None
        return (os.environ.get(var) if var else None) or os.environ.get("DISCORD_CHANNEL_ID") or None

    def target_for(self, route: str) -> tuple[str, str] | None:
        """("bot", channel_id) when a bot token and channel are set (messages get a Create-resume button),
        else ("webhook", url), else None."""
        if self.bot_token and (ch := self.channel_for(route)):
            return "bot", ch
        if url := self.webhook_for(route):
            return "webhook", url
        return None

    @property
    def resume(self) -> dict[str, Any]:
        return self.raw.get("resume", {})

    @property
    def db_path(self) -> Path:
        return ROOT / self.raw.get("database", "data/jobs.db")

    @property
    def jobs_dir(self) -> Path:
        """Per-job JSON written when an alert is sent. Plain files, so the resume bot on the host can read
        them even while the daemon runs in Docker (SQLite WAL isn't shared across the Docker Desktop VM)."""
        return self.db_path.parent / "jobs"


def load(prefs_path: Path | None = None, companies_path: Path | None = None) -> Settings:
    load_dotenv()
    prefs = yaml.safe_load((prefs_path or ROOT / "config/preferences.yaml").read_text())
    comp = yaml.safe_load((companies_path or ROOT / "config/companies.yaml").read_text())

    roles = prefs.get("roles", {})
    rel = RelevancePrefs(
        levels=set(roles.get("levels", ["intern", "new_grad"])),
        categories=set(roles.get("categories", ["software", "ai_ml", "research", "data", "quant"])),
        seasons=set(prefs.get("seasons") or []),
        allow_locations=set(prefs.get("locations", {}).get("allow", ["us", "remote_us", "remote", "unknown"])),
        accept_unleveled=bool(roles.get("accept_unleveled", False)),
        exclude_title_keywords=roles.get("exclude_title_keywords") or [],
        exclude_companies={c.lower() for c in roles.get("exclude_companies") or []},
    )

    src = prefs.get("sources", {})
    mult = MULTIPLIER.get(src.get("season_profile", "peak"), 1)
    mins = {"big_tech": 15, "tier1": 15, "tier2": 30, "tier3": 120, "slow": 60, "simplify": 20}
    mins.update(src.get("intervals_minutes") or {})

    reg = registry()
    connectors: list[Connector] = []
    intervals: dict[str, int] = {}
    directory: dict[str, tuple[str, str]] = {}
    for c in comp.get("companies", []):
        if not c.get("enabled", True):
            continue
        for name in [c["name"], *(c.get("aliases") or [])]:
            directory.setdefault(company_key(name), (c["id"], c.get("tier", "tier3")))
        for spec in c.get("connectors") or []:
            cls = reg.get(spec["kind"])
            if cls is None:
                continue
            conn = cls(kind=spec["kind"], slug=spec["slug"], company=c["name"], company_id=c["id"],
                       tier=c.get("tier", "tier3"), options=spec.get("options") or {})
            connectors.append(conn)
            group = "slow" if spec["kind"] in SLOW_KINDS else c.get("tier", "tier3")
            intervals[conn.key] = int(mins.get(group, 60)) * 60 * mult
    agg_every = int(mins.get("aggregators", 30)) * 60 * mult

    def add(kind: str, slug: str, every: int, **options) -> None:
        conn = reg[kind](kind=kind, slug=str(slug), company=options.get("name", kind.capitalize()), company_id="",
                         options=options)
        connectors.append(conn)
        intervals[conn.key] = every

    for feed in src.get("simplify_feeds", ["internships", "new-grad"]):
        add("simplify", feed, int(mins["simplify"]) * 60 * mult)
    for lst in src.get("markdown_lists") or []:
        add("markdown", lst, agg_every)
    if src.get("dover"):
        add("dover", "job-board", agg_every, name="Dover")
    if getro := src.get("getro"):
        for cid, name in (getro.get("collections") or {}).items():
            add("getro", cid, agg_every, name=str(name), job_functions=getro.get("job_functions"),
                seniority=getro.get("seniority"), locations=getro.get("locations"))
    if consider := src.get("consider"):
        for host, name in (consider.get("boards") or {}).items():
            add("consider", host, int(mins.get("consider", 20)) * 60 * mult, name=str(name),
                roles=consider.get("roles"))

    return Settings(
        raw=prefs, relevance=rel, connectors=connectors, intervals=intervals,
        likely_citizenship={x.lower() for x in prefs.get("eligibility", {}).get("likely_citizenship_companies") or []},
        directory=directory,
    )
