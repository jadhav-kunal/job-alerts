from __future__ import annotations

from ..http import Http
from ..normalize import strip_html
from . import Connector, FetchResult, parse_iso

API = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseConnector(Connector):
    """Light list call only; descriptions are fetched per new job (the content=true list is 20× larger)."""

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        r = await http.get(f"{API}/{self.slug}/jobs", etag=etag)
        if r.not_modified:
            return FetchResult(None, r.etag)
        jobs = []
        for j in r.data.get("jobs", []):
            loc = (j.get("location") or {}).get("name") or ""
            jobs.append(self.job(
                source_job_id=str(j["id"]),
                title=j["title"],
                url=j["absolute_url"],
                locations=[x.strip() for x in loc.replace(" | ", ";").split(";") if x.strip()],
                posted_at=parse_iso(j.get("first_published") or j.get("updated_at")),
                raw=j,
            ))
        return FetchResult(jobs, r.etag)


async def fetch_description(http: Http, org: str, job_id: str) -> str | None:
    r = await http.get(f"{API}/{org}/jobs/{job_id}", retries=1)
    return strip_html(r.data.get("content")) if r.data else None
