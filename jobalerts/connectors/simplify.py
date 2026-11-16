"""SimplifyJobs GitHub feeds: the coverage layer for Big Tech and ~700 companies outside our list (research §5.1)."""
from __future__ import annotations

from ..http import Http
from . import Connector, FetchResult, from_unix

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/.github/scripts/listings.json"

FEEDS = {
    # slug: (repo, level implied by the list)
    "internships": ("SimplifyJobs/Summer2027-Internships", "intern"),
    "new-grad": ("SimplifyJobs/New-Grad-Positions", "new_grad"),
    # Same listings.json format; links are go.vansh.nyc short links, resolved by the pipeline for new relevant jobs.
    "vansh-internships": ("vanshb03/Summer2027-Internships", "intern"),
    "vansh-new-grad": ("vanshb03/New-Grad-2027", "new_grad"),
}


class SimplifyConnector(Connector):
    """Built as SimplifyConnector("simplify", "internships", "Simplify", "")."""

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        repo, level = FEEDS[self.slug] if self.slug in FEEDS else (self.options["repo"], self.options.get("level"))
        url = RAW.format(repo=repo, branch=self.options.get("branch", "dev"))
        r = await http.get(url, etag=etag)
        if r.not_modified:
            return FetchResult(None, r.etag)
        if not isinstance(r.data, list) or len(r.data) < 100:
            # Sanity guard: a truncated or emptied feed must not look like "no jobs".
            raise ValueError(f"suspicious Simplify payload ({type(r.data).__name__}, {len(r.data or [])} rows)")
        jobs = []
        for j in r.data:
            if not (j.get("active") and j.get("is_visible", True)) or not j.get("url"):
                continue
            jobs.append(self.job(
                source_job_id=j["id"],
                title=j["title"],
                url=j["url"],
                locations=j.get("locations") or [],
                posted_at=from_unix(j.get("date_posted")),
                terms=j.get("terms") or [],
                category_hint=j.get("category"),
                level_hint=level,
                sponsorship=j.get("sponsorship"),
                raw=j,
            ))
        for job in jobs:          # Simplify rows carry their own company, not the connector's
            job.company = job.raw["company_name"]
            job.company_id = None
            job.tier = None
        return FetchResult(jobs, r.etag)
