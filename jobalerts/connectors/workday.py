from __future__ import annotations

import re

from ..http import Http
from ..normalize import strip_html
from . import Connector, FetchResult, parse_relative

DEFAULT_QUERIES = ["intern", "new grad", "university graduate", "early career", "entry level"]
PAGE = 20          # Workday CXS caps page size at 20


class WorkdayConnector(Connector):
    """slug = 'tenant/wdN/site'. No ETags, so we search only early-career terms, never the full board."""

    @property
    def _parts(self) -> tuple[str, str, str]:
        tenant, wd, site = self.slug.split("/")
        return tenant, wd, site

    @property
    def base(self) -> str:
        tenant, wd, _ = self._parts
        return f"https://{tenant}.{wd}.myworkdayjobs.com"

    @property
    def api(self) -> str:
        tenant, _, site = self._parts
        return f"{self.base}/wday/cxs/{tenant}/{site}"

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        seen: dict[str, object] = {}
        max_pages = int(self.options.get("max_pages", 5))
        for q in self.options.get("queries", DEFAULT_QUERIES):
            for page in range(max_pages):
                r = await http.post(f"{self.api}/jobs", {"appliedFacets": {}, "limit": PAGE,
                                                        "offset": page * PAGE, "searchText": q})
                postings = r.data.get("jobPostings") or []
                for p in postings:
                    path = p.get("externalPath") or ""
                    jid = (p.get("bulletFields") or [path.rsplit("_", 1)[-1]])[0]
                    if jid in seen:
                        continue
                    seen[jid] = self.job(
                        source_job_id=jid,
                        title=p["title"],
                        url=f"{self.base}/{self._parts[2]}{path}",
                        locations=_locations(p),
                        posted_at=parse_relative(p.get("postedOn")),
                        raw={**p, "_path": path},
                    )
                if len(postings) < PAGE or (page + 1) * PAGE >= (r.data.get("total") or 0):
                    break
        return FetchResult(list(seen.values()), None)  # type: ignore[arg-type]

    async def fetch_description(self, http: Http, job) -> str | None:
        r = await http.get(f"{self.api}{job.raw['_path']}", retries=1)
        info = (r.data or {}).get("jobPostingInfo") or {}
        return strip_html(info.get("jobDescription"))


def _locations(p: dict) -> list[str]:
    text = p.get("locationsText") or ""
    if text and not re.match(r"^\d+ Locations?$", text):
        return [text]
    # "N Locations" hides the list; the URL path carries the primary one, e.g. /job/US-CA-Santa-Clara/…
    m = re.match(r"/job/([^/]+)/", p.get("externalPath") or "")
    return [m[1].replace("---", ", ").replace("-", " ")] if m else []
