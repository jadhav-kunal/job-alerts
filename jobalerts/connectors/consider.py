"""VC portfolio job boards hosted on Consider (jobs.a16z.com). There is no JSON API: the newest jobs are embedded in the
Next.js page as "flight" data. Parsing approach from jobhunter's vc_sources.py (MIT).

Only the newest ~25 jobs per role page are in the HTML, so poll often enough that nothing scrolls past.
"""
from __future__ import annotations

import json
import re

from ..http import Http
from . import Connector, FetchResult, parse_iso

_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_JOBS_KEY = re.compile(r'"initialData"\s*:\s*\{\s*"jobs"\s*:\s*')


def parse_jobs(page: str) -> list[dict]:
    parts = []
    for literal in _FLIGHT.findall(page or ""):
        try:
            parts.append(json.loads(literal))
        except ValueError:
            continue
    text = "".join(parts)
    m = _JOBS_KEY.search(text)
    if not m:
        raise ValueError("no job list in the page; Consider may have changed its page format")
    jobs, _ = json.JSONDecoder().raw_decode(text, m.end())
    return [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []


class ConsiderConnector(Connector):
    """slug = board host (jobs.a16z.com); options: name, roles."""

    @property
    def key(self) -> str:
        return f"consider:{self.options.get('name', self.slug).lower()}"

    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        seen: dict[str, dict] = {}
        for role in self.options.get("roles") or ["software-engineer"]:
            text = await http.get_text(f"https://{self.slug}/jobs", params={"role": role})
            for j in parse_jobs(text):
                if j.get("id") and j.get("apply_url"):
                    seen.setdefault(str(j["id"]), j)
        jobs = []
        for jid, j in seen.items():
            locs = [str(x) for x in j.get("locations") or [j.get("location") or ""] if x]
            if j.get("remote") and not any("remote" in x.lower() for x in locs):
                locs.append("Remote")
            job = self.job(
                source_job_id=jid,
                title=str(j.get("title") or "").strip(),
                url=j["apply_url"],
                locations=locs,
                posted_at=parse_iso(j.get("posted_at") or j.get("created_at")),
                level_hint="intern" if j.get("is_internship") else None,
                raw={k: j.get(k) for k in ("id", "company_name", "is_internship")},
            )
            job.company = str(j.get("company_name") or "").strip() or "Unknown"
            job.company_id, job.tier = None, None
            jobs.append(job)
        return FetchResult(jobs)
