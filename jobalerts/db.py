"""SQLite store (WAL). One writer: the pipeline. Schema follows research §12, trimmed to what V1 uses."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    company TEXT,
    etag TEXT,
    seeded INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    last_success_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    circuit_open_until TEXT,
    last_error TEXT,
    last_fetched INTEGER
);

CREATE TABLE IF NOT EXISTS canonical_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    company_id TEXT,
    tier TEXT,
    title TEXT NOT NULL,
    apply_url TEXT NOT NULL,
    apply_url_rank INTEGER NOT NULL,
    normalized_url TEXT NOT NULL,
    ats TEXT, ats_org TEXT, ats_id TEXT,
    fingerprint TEXT NOT NULL,
    locations TEXT NOT NULL,
    terms TEXT,
    posted_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    relevant INTEGER NOT NULL,
    reason TEXT,
    level TEXT,
    category TEXT,
    flags TEXT,
    citizenship TEXT,
    citizenship_evidence TEXT,
    no_sponsorship INTEGER,
    description_snippet TEXT,
    description TEXT,          -- full text, relevant jobs only (fed to the resume builder)
    compensation TEXT
);
CREATE INDEX IF NOT EXISTS ix_cj_url ON canonical_jobs(normalized_url);
CREATE INDEX IF NOT EXISTS ix_cj_ats ON canonical_jobs(ats, ats_id);
CREATE INDEX IF NOT EXISTS ix_cj_fp ON canonical_jobs(fingerprint);
CREATE INDEX IF NOT EXISTS ix_cj_first_seen ON canonical_jobs(first_seen_at);

CREATE TABLE IF NOT EXISTS job_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_job_id INTEGER NOT NULL REFERENCES canonical_jobs(id),
    source TEXT NOT NULL,
    source_job_id TEXT NOT NULL,
    url TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (source, source_job_id)
);
CREATE INDEX IF NOT EXISTS ix_js_canonical ON job_sources(canonical_job_id);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_job_id INTEGER REFERENCES canonical_jobs(id),
    alert_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',     -- pending / sent / failed / suppressed
    attempts INTEGER NOT NULL DEFAULT 0,
    payload TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,              -- ok / not_modified / failed / skipped
    fetched INTEGER,
    new_jobs INTEGER,
    new_relevant INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(canonical_jobs)")}
        if "description" not in cols:
            self.conn.execute("ALTER TABLE canonical_jobs ADD COLUMN description TEXT")
        acols = {r[1] for r in self.conn.execute("PRAGMA table_info(alerts)")}
        if "message_id" not in acols:          # where the alert landed, so the bot can edit it and /todo link to it
            self.conn.execute("ALTER TABLE alerts ADD COLUMN message_id TEXT")
            self.conn.execute("ALTER TABLE alerts ADD COLUMN discord_channel_id TEXT")

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def one(self, sql: str, *args: Any) -> sqlite3.Row | None:
        return self.conn.execute(sql, args).fetchone()

    def all(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()

    def exec(self, sql: str, *args: Any) -> sqlite3.Cursor:
        return self.conn.execute(sql, args)

    # ── sources ──────────────────────────────────────────────────────────
    def source(self, key: str, kind: str, company: str) -> sqlite3.Row:
        self.exec("INSERT OR IGNORE INTO sources(key, kind, company) VALUES (?,?,?)", key, kind, company)
        return self.one("SELECT * FROM sources WHERE key=?", key)  # type: ignore[return-value]

    # ── kv ───────────────────────────────────────────────────────────────
    def get_kv(self, k: str) -> str | None:
        r = self.one("SELECT v FROM kv WHERE k=?", k)
        return r["v"] if r else None

    def set_kv(self, k: str, v: str) -> None:
        self.exec("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, v)


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
