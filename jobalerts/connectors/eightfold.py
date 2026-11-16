from __future__ import annotations

from ..http import Http
from . import Connector, FetchResult, from_unix

DEFAULT_QUERIES = ["intern", "new grad", "university", "early career"]


class EightfoldConnector(Connector):
    """slug = career-site host, options.domain = the company domain (Netflix: explore.jobs.netflix.net / netflix.com)."""

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        seen = {}
        domain = self.options.get("domain", f"{self.company_id}.com")
        for q in self.options.get("queries", DEFAULT_QUERIES):
            r = await http.get(f"https://{self.slug}/api/apply/v2/jobs",
                               params={"domain": domain, "start": 0, "num": 100, "query": q})
            for p in r.data.get("positions", []):
                jid = str(p["id"])
                if jid in seen:
                    continue
                seen[jid] = self.job(
                    source_job_id=jid,
                    title=p.get("posting_name") or p["name"],
                    url=p.get("canonicalPositionUrl") or f"https://{self.slug}/careers/job/{jid}",
                    locations=p.get("locations") or [p.get("location") or ""],
                    posted_at=from_unix(p.get("t_create")),
                    description=p.get("job_description") or None,
                    department=p.get("department"),
                    raw=p,
                )
        return FetchResult(list(seen.values()), None)
