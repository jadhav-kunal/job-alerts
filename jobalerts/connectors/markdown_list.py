"""GitHub job lists published as Markdown/HTML tables (speedyapply/2027-SWE-College-Jobs). Each row links straight to
the company's ATS, so descriptions can be fetched the same way as for Simplify rows.

    | <a href="https://meta.com"><strong>Meta</strong></a> | Research Intern | Redmond, WA | $50/hr | <a href="…">…</a> | 3d |

The salary column is optional; the posting link is the cell with an <a href>, and the last cell is the age ("3d").
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone

from ..http import Http
from ..normalize import normalize_url
from . import Connector, FetchResult

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
LISTS = {
    # slug: (repo, branch, path, level implied by the list)
    "speedyapply-internships": ("speedyapply/2027-SWE-College-Jobs", "main", "README.md", "intern"),
    "speedyapply-new-grad": ("speedyapply/2027-SWE-College-Jobs", "main", "NEW_GRAD_USA.md", "new_grad"),
}
_HREF = re.compile(r'href="([^"]+)"')
_TAG = re.compile(r"<[^>]+>")
_AGE = re.compile(r"^(\d+)\s*([dhwm]o?)$")


def _text(cell: str) -> str:
    return html.unescape(_TAG.sub("", cell)).strip().strip("*").strip()


def parse_rows(md: str) -> list[dict]:
    rows = []
    for line in md.splitlines():
        if not line.startswith("| <a") and not line.startswith("| **"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) < 4:
            continue
        posting = next((c for c in cells[3:] if _HREF.search(c)), None)
        if posting is None:
            continue
        rows.append({
            "company": _text(cells[0]),
            "title": _text(cells[1]),
            "location": _text(cells[2]),
            "url": html.unescape(_HREF.search(posting)[1]),
            "salary": _text(cells[3]) if cells[3] is not posting and len(cells) >= 6 else None,
            "age": _text(cells[-1]),
        })
    return rows


def _posted(age: str) -> datetime | None:
    m = _AGE.match(age.lower())
    if not m:
        return None
    n, unit = int(m[1]), m[2]
    days = {"d": n, "h": n / 24, "w": 7 * n, "mo": 30 * n, "m": 30 * n}[unit]
    return datetime.now(timezone.utc) - timedelta(days=days)


class MarkdownListConnector(Connector):
    async def fetch(self, http: Http, etag: str | None) -> FetchResult:
        repo, branch, path, level = LISTS[self.slug] if self.slug in LISTS else (
            self.options["repo"], self.options.get("branch", "main"), self.options["path"], self.options.get("level"))
        rows = parse_rows(await http.get_text(RAW.format(repo=repo, branch=branch, path=path)))
        if len(rows) < 20:
            # Same guard as Simplify: a reformatted or emptied list must not look like "no jobs".
            raise ValueError(f"only {len(rows)} rows parsed from {repo}/{path}; did the table format change?")
        jobs = []
        for r in rows:
            locs = [x.strip() for x in re.split(r";|<br>|\s/\s", r["location"]) if x.strip()]
            job = self.job(
                source_job_id=hashlib.sha1(normalize_url(r["url"]).encode()).hexdigest()[:16],
                title=r["title"],
                url=r["url"],
                locations=[re.sub(r"\s*\+\d+$", "", x) for x in locs],
                posted_at=_posted(r["age"]),
                compensation=r["salary"] if r["salary"] and r["salary"] != "-" else None,
                level_hint=level,
                raw=r,
            )
            job.company, job.company_id, job.tier = r["company"], None, None
            jobs.append(job)
        return FetchResult(jobs)
