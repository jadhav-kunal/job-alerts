"""Which alerts you have applied to, saved for later or skipped.

An append-only JSON-lines file, data/applications.jsonl, one event per click:

    {"job_id": 27701, "status": "applied", "at": "2026-10-29T23:10:04+00:00", "via": "discord"}

The resume bot on the host is the only writer (Discord buttons and the browser-extension helper both run inside it).
The daemon in Docker only reads it, for the daily summary. A plain file instead of SQLite because SQLite's WAL is not
shared across the Docker Desktop VM boundary. The latest event per job wins; status "none" clears it.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"applied": "✅ Applied", "later": "⭐ Saved for later", "skip": "⏭ Skipped"}


def path_for(jobs_dir: Path) -> Path:
    return jobs_dir.parent / "applications.jsonl"


class Tracker:
    def __init__(self, path: Path):
        self.path = path
        self._status: dict[int, dict] = {}
        self._mtime = -1.0

    def _load(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._status, self._mtime = {}, -1.0
            return
        if mtime == self._mtime:
            return
        status: dict[int, dict] = {}
        for line in self.path.read_text().splitlines():
            try:
                ev = json.loads(line)
                status[int(ev["job_id"])] = ev
            except (ValueError, KeyError, TypeError):
                continue                      # a half-written last line after a crash
        self._status = {k: v for k, v in status.items() if v.get("status") in STATUSES}
        self._mtime = mtime

    def get(self, job_id: int) -> dict | None:
        self._load()
        return self._status.get(job_id)

    def all(self) -> dict[int, dict]:
        self._load()
        return dict(self._status)

    def set(self, job_id: int, status: str, via: str = "discord") -> dict:
        """Record a status ("applied" / "later" / "skip", or "none" to clear). Returns the event."""
        if status not in STATUSES and status != "none":
            raise ValueError(f"unknown status {status!r}")
        ev = {"job_id": int(job_id), "status": status,
              "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "via": via}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One write() on an O_APPEND file: a line never interleaves with another writer's.
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(ev) + "\n").encode())
        finally:
            os.close(fd)
        self._mtime = -1.0                    # re-read next time, even if the mtime tick did not change
        return ev
