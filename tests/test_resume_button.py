import asyncio
import json
import sqlite3

from jobalerts import discord, resume
from jobalerts.db import SCHEMA, Store

from test_pipeline import Fake, job, make


def _one_alerted_job(tmp_path):
    pipe, db = make(tmp_path, [])
    src = Fake("greenhouse", "anthropic", [job(title="Machine Learning Engineer, New Grad",
                                                description="Train models with PyTorch. " * 30)])
    pipe.s.connectors = [src]
    pipe._by_key = {src.key: src}
    asyncio.run(pipe.run_source(src))
    cid = db.one("SELECT canonical_job_id FROM alerts WHERE alert_type='new'")[0]
    pipe.s.raw["database"] = str(tmp_path / "t.db")
    return pipe.s, db, cid


def test_target_prefers_bot_when_configured(tmp_path, monkeypatch):
    s, _, _ = _one_alerted_job(tmp_path)
    s.raw["alerts"]["routes"] = {"intern": "DISCORD_WEBHOOK_INTERNSHIPS"}
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert s.target_for("intern") == ("webhook", "https://discord.com/api/webhooks/1/x")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "111")
    assert s.target_for("intern") == ("bot", "111")
    monkeypatch.setenv("DISCORD_CHANNEL_INTERNSHIPS", "222")
    assert s.target_for("intern") == ("bot", "222")


def test_full_description_stored_and_exported(tmp_path):
    s, db, cid = _one_alerted_job(tmp_path)
    discord.export_job(s, db, cid)
    rec = json.loads((s.jobs_dir / f"{cid}.json").read_text())
    assert rec["description_is_full"] and rec["description"].count("PyTorch") == 30
    assert resume.load_job(s, cid)["title"] == "Machine Learning Engineer, New Grad"
    md = resume.job_markdown(rec)
    assert "Apply URL: https://job-boards.greenhouse.io/anthropic/jobs/111" in md and "Partial" not in md


def test_bot_mode_drain_adds_buttons(tmp_path, monkeypatch):
    s, db, cid = _one_alerted_job(tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "111")
    monkeypatch.setattr(discord, "SEND_GAP", 0)
    sent = []

    async def fake_post(client, dest, payload, bot_token=None):
        sent.append((dest, payload, bot_token))
        return {"id": "999", "channel_id": dest}
    monkeypatch.setattr(discord, "post", fake_post)
    assert asyncio.run(discord.drain(s, db)) == 1
    dest, payload, token = sent[0]
    assert (dest, token) == ("111", "tok")
    row1, row2 = (r["components"] for r in payload["components"])
    assert [b["custom_id"] for b in row1[:3]] == [f"status:applied:{cid}", f"status:later:{cid}", f"status:skip:{cid}"]
    assert row1[3]["url"].startswith("https://job-boards.greenhouse.io/")
    assert [b["custom_id"] for b in row2] == [f"resume:{cid}", f"cover:{cid}"]
    rec = json.loads((s.jobs_dir / f"{cid}.json").read_text())
    assert (rec["message_id"], rec["discord_channel_id"], rec["route"]) == ("999", "111", "other")


def test_names_are_filesystem_safe(tmp_path):
    s, _, _ = _one_alerted_job(tmp_path)
    s.raw["resume"] = {"output_dir": str(tmp_path / "out"), "file_prefix": "Jane_Doe_Resume"}
    j = {"id": 7, "company": "Jane Street / NYC", "title": "SWE (New Grad) – 2027"}
    assert resume.job_folder(s, j).name == "Jane_Street_NYC_SWE_New_Grad_2027_7"
    assert resume.pdf_name(s, j) == "Jane_Doe_Resume_Jane_Street_NYC.pdf"


def test_old_database_gets_description_column(tmp_path):
    p = tmp_path / "old.db"
    old_schema = "\n".join(line for line in SCHEMA.splitlines() if not line.strip().startswith("description TEXT"))
    c = sqlite3.connect(p)
    c.executescript(old_schema)
    c.close()
    Store(p)
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(canonical_jobs)")}
    assert "description" in cols
