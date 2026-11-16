"""How many Claude tokens the resume, cover letter and answer runs use.

Every `claude -p --output-format json` run reports its usage; record() appends one line per run to
data/claude_usage.jsonl and summary() adds them up (`python -m jobalerts usage`). The dollar figure is Claude's list
price for those tokens: on a Pro/Max subscription you are not billed per token, it shows how much of your plan's
usage the runs take relative to each other.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT

USAGE_FILE = ROOT / "data/claude_usage.jsonl"


def parse(out: bytes | str) -> dict | None:
    """Tokens and cost from a `claude -p --output-format json` reply (None if it has none)."""
    try:
        res = json.loads(out)
    except (ValueError, TypeError):
        return None
    u = res.get("usage") or {}
    if not u and "total_cost_usd" not in res:
        return None
    return {"input": int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0),
            "cached": int(u.get("cache_read_input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
            "cost_usd": round(float(res.get("total_cost_usd") or 0), 4),
            "seconds": round((res.get("duration_ms") or 0) / 1000, 1),
            "models": sorted((res.get("modelUsage") or {}).keys())}


def record(kind: str, job_id: int | None, out: bytes | str, provider: str = "claude") -> dict | None:
    u = parse(out)
    if u is None:
        return None
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, "job_id": job_id,
           "provider": provider, **u}
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return u


def rows(path: Path = USAGE_FILE) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def summary(path: Path = USAGE_FILE, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    data = rows(path)
    if not data:
        return "No Claude runs recorded yet (data/claude_usage.jsonl)."
    lines = ["Claude usage (list-price equivalent; a subscription is not billed per token)", ""]
    for title, since in (("Last 24 hours", now - timedelta(days=1)), ("Last 7 days", now - timedelta(days=7)),
                         ("All recorded", None)):
        part = [r for r in data if since is None or datetime.fromisoformat(r["at"]) >= since]
        lines.append(f"{title}: {len(part)} run(s)")
        for kind, provider in sorted({(r["kind"], r.get("provider", "claude")) for r in part}):
            k = [r for r in part if r["kind"] == kind and r.get("provider", "claude") == provider]
            tot = lambda f: sum(r.get(f, 0) for r in k)
            lines.append(f"  {kind + ' (' + provider + ')':22} {len(k):4} runs  {tot('input'):>10,} in  {tot('cached'):>11,} cached  "
                         f"{tot('output'):>9,} out  ${tot('cost_usd'):8.2f}  avg {tot('seconds') / len(k):5.0f}s")
        lines.append("")
    return "\n".join(lines).rstrip()


def backfill(resumes_root: Path) -> int:
    """Record runs made before tracking existed, from the saved claude logs (once; skips if any rows exist)."""
    if rows():
        return 0
    n = 0
    names = {"claude.log": "resume", "cover_letter_claude.log": "cover_letter", "answers_claude.log": "answers"}
    found = []
    for log_name, kind in names.items():
        for log in resumes_root.glob(f"**/{log_name}"):
            found.append((log.stat().st_mtime, log, kind))
    for mtime, log, kind in sorted(found):
        raw = log.read_text(errors="replace").split("\n--- stderr ---")[0]
        u = parse(raw)
        if u is None:
            continue
        tail = log.parent.name if kind != "answers" else log.parent.parent.parent.name
        job_id = int(tail.rsplit("_", 1)[-1]) if tail.rsplit("_", 1)[-1].isdigit() else None
        row = {"at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds"), "kind": kind,
               "job_id": job_id, "provider": "claude", **u}
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_FILE.open("a") as f:
            f.write(json.dumps(row) + "\n")
        n += 1
    return n
