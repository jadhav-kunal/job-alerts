from __future__ import annotations

from ..http import Http
from . import Connector, FetchResult, parse_iso

API = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyConnector(Connector):
    """Descriptions come free in the list call."""

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        r = await http.get(f"{API}/{self.slug}", params={"includeCompensation": "true"}, etag=etag)
        if r.not_modified:
            return FetchResult(None, r.etag)
        return FetchResult([self._to_job(j) for j in r.data.get("jobs", []) if j.get("isListed", True)], r.etag)

    def _to_job(self, j: dict):
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        if j.get("isRemote") and not any("remote" in x.lower() for x in locs):
            locs.append("Remote")
        comp = (j.get("compensation") or {}).get("compensationTierSummary")
        return self.job(
            source_job_id=j["id"],
            title=j["title"],
            url=j.get("jobUrl") or j.get("applyUrl"),
            locations=[x for x in locs if x],
            posted_at=parse_iso(j.get("publishedAt")),
            description=j.get("descriptionPlain"),
            department=j.get("department"),
            employment_type=j.get("employmentType"),
            compensation=comp,
            raw={k: v for k, v in j.items() if k not in ("descriptionHtml", "descriptionPlain")},
        )


async def fetch_board_descriptions(http: Http, org: str) -> dict[str, str]:
    """Used to enrich Simplify jobs that point at an Ashby board we don't poll directly."""
    r = await http.get(f"{API}/{org}", retries=1)
    return {j["id"]: j.get("descriptionPlain") or "" for j in (r.data or {}).get("jobs", [])}
