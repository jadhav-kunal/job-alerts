"""Source connectors. Each one turns a public JSON endpoint into NormalizedJob records."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..http import Http
from ..models import NormalizedJob


@dataclass
class FetchResult:
    jobs: list[NormalizedJob] | None      # None → 304 Not Modified, nothing to do
    etag: str | None = None


@dataclass
class Connector:
    """Base class. `key` is the unique source id stored in the DB, e.g. 'greenhouse:anthropic'."""
    kind: str
    slug: str
    company: str
    company_id: str
    tier: str = "tier3"
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.slug}"

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        raise NotImplementedError

    def job(self, **kw) -> NormalizedJob:
        return NormalizedJob(source=self.key, company=self.company, company_id=self.company_id,
                             tier=self.tier, **kw)


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def from_unix(v: float | int | str | None, ms: bool = False) -> datetime | None:
    try:
        v = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(v / 1000 if ms else v, tz=timezone.utc)


def parse_relative(s: str | None) -> datetime | None:
    """Workday 'Posted Today' / 'Posted Yesterday' / 'Posted 7 Days Ago' / 'Posted 30+ Days Ago'."""
    if not s:
        return None
    now = datetime.now(timezone.utc)
    low = s.lower()
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    if m := re.search(r"(\d+)\+?\s*day", low):
        return now - timedelta(days=int(m[1]))
    return None


def registry() -> dict[str, type[Connector]]:
    from .amazon import AmazonConnector
    from .ashby import AshbyConnector
    from .consider import ConsiderConnector
    from .dover import DoverConnector
    from .eightfold import EightfoldConnector
    from .getro import GetroConnector
    from .greenhouse import GreenhouseConnector
    from .lever import LeverConnector
    from .markdown_list import MarkdownListConnector
    from .rippling import RipplingConnector
    from .simplify import SimplifyConnector
    from .workday import WorkdayConnector
    return {
        "greenhouse": GreenhouseConnector, "ashby": AshbyConnector, "lever": LeverConnector,
        "workday": WorkdayConnector, "amazon": AmazonConnector, "eightfold": EightfoldConnector,
        "rippling": RipplingConnector, "simplify": SimplifyConnector,
        # aggregators: many companies per source, company comes from each row
        "getro": GetroConnector, "consider": ConsiderConnector, "dover": DoverConnector,
        "markdown": MarkdownListConnector,
    }


AGGREGATORS = {"simplify", "getro", "consider", "dover", "markdown"}
