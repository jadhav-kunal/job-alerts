from __future__ import annotations

from datetime import datetime, timezone

from ..http import Http
from ..normalize import strip_html
from . import Connector, FetchResult

API = "https://www.amazon.jobs/en/search.json"
DEFAULT_QUERIES = [
    "software development engineer intern", "machine learning intern", "applied scientist intern",
    "research scientist intern", "data scientist intern", "data engineer intern",
    "software development engineer new grad", "university graduate", "sde I",
]


class AmazonConnector(Connector):
    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        seen = {}
        for q in self.options.get("queries", DEFAULT_QUERIES):
            r = await http.get(API, params={
                "base_query": q, "normalized_country_code[]": "USA",
                "result_limit": 100, "offset": 0, "sort": "recent",
            })
            for j in r.data.get("jobs", []):
                jid = str(j.get("id_icims") or j["id"])
                if jid in seen:
                    continue
                desc = "\n\n".join(filter(None, [j.get("description"), j.get("basic_qualifications"),
                                                 j.get("preferred_qualifications")]))
                seen[jid] = self.job(
                    source_job_id=jid,
                    title=j["title"],
                    url=f"https://www.amazon.jobs{j['job_path']}",
                    locations=[j.get("location") or ""],
                    posted_at=_date(j.get("posted_date")),
                    description=strip_html(desc),
                    department=j.get("job_category"),
                    raw={k: v for k, v in j.items() if k not in ("description", "basic_qualifications",
                                                                 "preferred_qualifications", "description_short")},
                )
        return FetchResult(list(seen.values()), None)


def _date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(" ".join(s.split()), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
