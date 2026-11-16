import asyncio
import json
from datetime import date, datetime, timedelta, timezone

from aiohttp.test_utils import TestClient, TestServer

from jobalerts import cover_letter, helper
from jobalerts.bot import decorate, todo_lines
from jobalerts.tracker import Tracker

NOW = datetime.now(timezone.utc)


def test_tracker_latest_event_wins_and_none_clears(tmp_path):
    t = Tracker(tmp_path / "applications.jsonl")
    t.set(1, "later")
    t.set(1, "applied")
    t.set(2, "skip")
    t.set(2, "none")
    assert t.get(1)["status"] == "applied" and t.get(2) is None
    (tmp_path / "applications.jsonl").open("a").write('{"job_id": 3, "sta')   # torn last line after a crash
    assert set(Tracker(tmp_path / "applications.jsonl").all()) == {1}


def test_decorate_marks_and_restores():
    base = {"title": "Software Engineer, New Grad", "color": 0x22C55E, "footer": {"text": "job #7 · greenhouse 123"}}
    applied = decorate(base, "applied", 0x22C55E, datetime(2026, 10, 29))
    assert applied["title"] == "✅ Software Engineer, New Grad"
    assert applied["footer"]["text"] == "job #7 · greenhouse 123 · ✅ Applied Oct 29"
    assert applied["color"] != 0x22C55E
    later = decorate(applied, "later", 0x22C55E, datetime(2026, 10, 30))     # switching replaces, never stacks
    assert later["title"] == "⭐ Software Engineer, New Grad" and later["footer"]["text"].count("·") == 2
    assert decorate(later, None, 0x22C55E) == base


def _job(i, route, hours_ago, **kw):
    return {"id": i, "company": f"Co{i}", "title": f"SWE {i}", "apply_url": f"https://x.com/{i}", "route": route,
            "sent_at": (NOW - timedelta(hours=hours_ago)).isoformat(), **kw}


def test_todo_lists_untouched_and_later_oldest_first():
    jobs = [_job(1, "tier1", 5), _job(2, "tier1", 30, message_id="m2", discord_channel_id="c1"),
            _job(3, "big_tech", 2), _job(4, "tier1", 1), _job(5, "tier1", 24 * 30)]
    statuses = {4: {"status": "applied"}, 1: {"status": "later"}}
    lines, counts = todo_lines(jobs, statuses, "tier1", 14, True, 99)
    assert counts == {"tier1": 2, "big_tech": 1}                         # #5 is older than 14 days, #4 applied
    assert lines[0].startswith("[Co2 · SWE 2](https://discord.com/channels/99/c1/m2) · 1d")
    assert lines[1].startswith("⭐ [Co1 · SWE 1](https://x.com/1)")
    assert todo_lines(jobs, statuses, "tier1", 14, False, 99)[1] == {"tier1": 1, "big_tech": 1}


def test_match_by_url_and_ats_id():
    jobs = [{"id": 1, "apply_url": "https://job-boards.greenhouse.io/stripe/jobs/7001"},
            {"id": 2, "apply_url": "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c"},
            {"id": 3, "apply_url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/X/Intern_JR2024692"}]
    assert helper.match(jobs, "https://boards.greenhouse.io/stripe/jobs/7001?gh_src=x")["id"] == 1
    assert helper.match(jobs, "https://stripe.com/jobs/listing/swe/7001?gh_jid=7001")["id"] == 1
    assert helper.match(jobs, "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c/apply")["id"] == 2
    assert helper.match(jobs, "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/X/"
                              "Intern_JR2024692/apply/applyManually")["id"] == 3
    assert helper.match(jobs, "https://example.com/careers") is None


class FakeBot:
    def __init__(self, tmp_path):
        self.tracker = Tracker(tmp_path / "applications.jsonl")
        self.in_progress = set()
        self.calls = []
        job = {"id": 5, "company": "Stripe", "title": "SWE", "apply_url": "https://job-boards.greenhouse.io/stripe/jobs/5"}
        self.jobs = type("J", (), {"all": lambda s: [job], "get": lambda s, i: job if i == 5 else None})()
        self.settings = None

    def existing(self, kind, job):
        return None

    async def set_status_from_helper(self, job_id, status):
        self.tracker.set(job_id, status, via="extension")


def test_helper_requires_token_and_records_status(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, "TOKEN_FILE", tmp_path / "token")
    monkeypatch.setattr(helper, "_default_resume", lambda: None)
    bot = FakeBot(tmp_path)

    async def go():
        async with TestClient(TestServer(helper.build_app(bot))) as c:
            assert (await c.get("/api/ping")).status == 401
            h = {"X-Job-Alerts-Token": helper.token()}
            r = await (await c.get("/api/match", params=[("url", "https://other.com"),
                                                         ("url", "https://boards.greenhouse.io/stripe/jobs/5")],
                                   headers=h)).json()
            assert r["found"] and r["job"]["company"] == "Stripe" and r["status"] is None
            assert (await c.post("/api/status", json={"job_id": 5, "status": "applied"}, headers=h)).status == 200
            r = await (await c.get("/api/match", params={"url": "https://job-boards.greenhouse.io/stripe/jobs/5"},
                                   headers=h)).json()
            assert r["status"] == "applied"
    asyncio.run(go())


def test_cover_letter_render_escapes_and_has_no_dashes():
    prof = {"name": {"first": "Jane", "last": "Doe"}, "email": "k@x.com", "phone": "+1 970",
            "links": {"github": "https://github.com/janedoe", "linkedin": "https://linkedin.com/in/janedoe"}}
    tex, txt = cover_letter.render({"salutation": "Hiring Team", "company_line": "AT&T Labs",
                                    "paragraphs": ["Cut p99 latency 40% — at scale_ok.", "Second."]},
                                   prof, date(2026, 10, 29))
    assert r"AT\&T Labs" in tex and r"40\%, at scale\_ok." in tex and "—" not in tex
    assert "October 29, 2026" in tex and "Github/janedoe" in tex and "<<" not in tex
    assert txt.startswith("Dear Hiring Team,") and txt.endswith("Sincerely,\nJane Doe") and "—" not in txt
    assert json.loads(json.dumps(txt))


def test_answers_cleaning():
    from jobalerts.answers import clean_answers
    qs = [{"key": "q0", "type": "choice", "options": ["Yes", "No"]},
          {"key": "q1", "type": "long_text"}, {"key": "q2", "type": "choice", "options": ["A", "B"]}]
    data = {"answers": [{"key": "q0", "answer": "yes"}, {"key": "q1", "answer": "Built X — shipped Y"},
                        {"key": "q2", "answer": "C"}, {"key": "zz", "answer": "x"}], "notes": "n"}
    assert clean_answers(data, qs) == [{"key": "q0", "answer": "Yes"}, {"key": "q1", "answer": "Built X, shipped Y"},
                                       {"key": "q2", "answer": None}]


def test_answers_fit_form_limits():
    from jobalerts.answers import clean_answers, fit_to
    essay = ("I built a retrieval system over SEC filings. It cites every sentence. It refuses instead of guessing when "
             "the evidence is missing, which matters for finance.")
    assert fit_to(essay) == essay
    assert fit_to(essay, max_length=80) == "I built a retrieval system over SEC filings. It cites every sentence."
    assert fit_to(essay, max_words=10) == "I built a retrieval system over SEC filings."
    assert fit_to("one two three four five six seven eight nine ten", max_length=20) == "one two three four"
    qs = [{"key": "q0", "type": "long_text", "max_length": 80}, {"key": "q1", "type": "long_text", "max_words": 500}]
    got = clean_answers({"answers": [{"key": "q0", "answer": essay}, {"key": "q1", "answer": essay}]}, qs)
    assert got == [{"key": "q0", "answer": "I built a retrieval system over SEC filings. It cites every sentence.",
                    "shortened": True}, {"key": "q1", "answer": essay}]
