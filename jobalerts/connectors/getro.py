"""VC portfolio job boards hosted on Getro (Accel, General Catalyst, Thrive, Lux, 8VC, ...): thousands of startups
behind one public search API. Idea and endpoint from jobhunter's vc_sources.py (MIT).

One connector per collection. Getro's own seniority tags narrow the search to internships and entry-level roles, but
they are guesses, so the title still decides (no level hint is passed on).
"""
from __future__ import annotations

from ..http import Http
from . import Connector, FetchResult, from_unix

API = "https://api.getro.com/api/v2/collections/{id}/search/jobs"
PAGE_SIZE, MAX_PAGES = 20, 25          # Getro caps a page at 20 jobs


class GetroConnector(Connector):
    """slug = collection id; options: name, job_functions, seniority, locations."""

    @property
    def key(self) -> str:
        return f"getro:{self.options.get('name', self.slug).lower().replace(' ', '-')}"

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        filters: dict = {"job_functions": self.options.get("job_functions") or ["Software Engineering"]}
        if seniority := self.options.get("seniority"):
            filters["seniority"] = seniority
        if locations := self.options.get("locations"):
            filters["searchable_locations"] = locations
        raw: list[dict] = []
        for page in range(MAX_PAGES):
            r = await http.post(API.format(id=self.slug),
                                {"hitsPerPage": PAGE_SIZE, "page": page, "query": "", "filters": filters})
            res = (r.data or {}).get("results") or {}
            batch = [j for j in res.get("jobs") or [] if isinstance(j, dict) and j.get("id") and j.get("url")]
            raw += batch
            if len(batch) < PAGE_SIZE or len(raw) >= int(res.get("count") or 0):
                break
        jobs = []
        for j in raw:
            job = self.job(
                source_job_id=str(j["id"]),
                title=str(j.get("title") or "").strip(),
                url=j["url"],
                locations=[str(x) for x in j.get("locations") or []],
                posted_at=from_unix(j.get("created_at")),
                raw={k: j.get(k) for k in ("id", "seniority", "work_mode", "source")},
            )
            job.company = str((j.get("organization") or {}).get("name") or "").strip() or "Unknown"
            job.company_id, job.tier = None, None
            jobs.append(job)
        return FetchResult(jobs)
