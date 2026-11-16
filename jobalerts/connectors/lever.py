from __future__ import annotations

from ..http import Http
from ..normalize import strip_html
from . import Connector, FetchResult, from_unix

API = "https://api.lever.co/v0/postings"


def _description(j: dict) -> str:
    parts = [j.get("openingPlain") or j.get("descriptionPlain") or "", j.get("descriptionBodyPlain") or ""]
    for lst in j.get("lists") or []:
        parts.append(lst.get("text", ""))
        parts.append(lst.get("content", ""))
    parts.append(j.get("additionalPlain") or "")
    return strip_html("\n".join(p for p in parts if p)) or ""


class LeverConnector(Connector):
    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        r = await http.get(f"{API}/{self.slug}", params={"mode": "json"}, etag=etag)
        if r.not_modified:
            return FetchResult(None, r.etag)
        jobs = []
        for j in r.data:
            cats = j.get("categories") or {}
            locs = cats.get("allLocations") or [cats.get("location") or ""]
            if j.get("workplaceType") == "remote" and not any("remote" in x.lower() for x in locs):
                locs = [*locs, "Remote"]
            jobs.append(self.job(
                source_job_id=j["id"],
                title=j["text"],
                url=j.get("hostedUrl") or j.get("applyUrl"),
                locations=[x for x in locs if x],
                posted_at=from_unix(j.get("createdAt"), ms=True),
                description=_description(j),
                department=cats.get("team") or cats.get("department"),
                employment_type=cats.get("commitment"),
                raw={k: v for k, v in j.items() if not k.startswith(("description", "additional", "opening", "lists"))},
            ))
        return FetchResult(jobs, r.etag)


async def fetch_description(http: Http, org: str, job_id: str) -> str | None:
    r = await http.get(f"{API}/{org}/{job_id}", retries=1)
    return _description(r.data) if r.data else None
