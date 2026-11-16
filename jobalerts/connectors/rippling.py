from __future__ import annotations

from ..http import Http
from . import Connector, FetchResult

API = "https://api.rippling.com/platform/api/ats/v1/board"


class RipplingConnector(Connector):
    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        r = await http.get(f"{API}/{self.slug}/jobs", etag=etag)
        if r.not_modified:
            return FetchResult(None, r.etag)
        jobs = []
        for j in r.data:
            loc = j.get("workLocation") or {}
            jobs.append(self.job(
                source_job_id=j["uuid"],
                title=j["name"],
                url=j["url"],
                locations=[loc.get("label") or ""],
                department=(j.get("department") or {}).get("label"),
                raw=j,
            ))
        return FetchResult(jobs, r.etag)
