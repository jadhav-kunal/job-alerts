import asyncio

import pytest

from jobalerts import citizenship
from jobalerts.config import Settings
from jobalerts.connectors.consider import parse_jobs
from jobalerts.connectors.markdown_list import parse_rows
from jobalerts.db import Store
from jobalerts.employment import contract_or_hourly
from jobalerts.normalize import company_key
from jobalerts.pipeline import Pipeline
from jobalerts.relevance import RelevancePrefs
from jobalerts.years import required_years
from test_pipeline import Fake, job

EXCLUDE = {"contract", "hourly"}


# ── years of experience (jobhunter's parser) ──────────────────────────────
@pytest.mark.parametrize("text,years", [
    ("Requirements:\n- 3+ years of experience with Python", 3),
    ("0-2 years of professional software experience", 0),
    ("BS in CS. With 40+ years of experience helping clients, we're a leader.", None),
    ("5+ years of experience preferred.", None),
    ("Minimum 5 years of experience, or 2 years with a Master's degree.", 2),
    ("Must be 18 years or older.", None),
])
def test_required_years(text, years):
    assert required_years(text) == years


# ── contract / hourly ─────────────────────────────────────────────────────
@pytest.mark.parametrize("title,desc,reason", [
    ("Software Engineer - C2C", "", "contract: c2c"),
    ("Junior Developer", "This is a 6-month contract role.", "contract: contract role"),
    ("Entry Level Software Engineer", "Pay: $28/hr, W2 only", "contract: w2 only"),
    ("Software Engineer, New Grad", "Compensation: $35/hr", "hourly pay: $35/hr"),
])
def test_contract_and_hourly_dropped(title, desc, reason):
    assert contract_or_hourly(title, desc, EXCLUDE) == reason


@pytest.mark.parametrize("title,desc", [
    ("Software Engineer Intern", "Pay: $45/hr"),                   # interns are usually hourly
    ("Smart Contract Engineer, New Grad", "Write Solidity."),
    ("Software Engineer, New Grad", "Contract-to-hire after 6 months."),
    ("Software Engineer I", "We process 10,000/hr transactions."),
])
def test_contract_and_hourly_kept(title, desc):
    assert contract_or_hourly(title, desc, EXCLUDE) is None


# ── citizenship / clearance wording ───────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Requires an active Secret clearance.",
    "This role requires a TS/SCI clearance.",
    "Must be eligible for a security clearance.",
    "Candidates must pass a background investigation and obtain a Public Trust clearance.",
    "This position is open to U.S. citizens only.",
    "Must possess U.S. citizenship.",
    "Minimum Clearance Required to Start: Secret",
])
def test_clearance_and_citizenship_rejected(text):
    assert citizenship.check(text).status == "reject"


@pytest.mark.parametrize("text", [
    "We consider all applicants without regard to national origin, citizenship status, or disability.",
    "Must be authorized to work in the United States.",
    "Employee Polygraph Protection Act poster.",
    "Minimum Clearance Required to Start: None",
    "You'll build our customs clearance product. You must know Python.",
])
def test_eligibility_near_misses_ok(text):
    assert citizenship.check(text).status == "ok"


def test_preferred_clearance_only_warns():
    assert citizenship.check("An active Secret clearance is a plus.").status == "warn"


# ── aggregator parsing ────────────────────────────────────────────────────
def test_speedyapply_rows():
    md = ('| Company | Position | Location | Salary | Posting | Age |\n|---|---|---|---|---|---|\n'
          '| <a href="https://www.twitch.tv"><strong>Twitch</strong></a> | Software Engineer I | San Francisco, CA | '
          '$193k/yr | <a href="https://job-boards.greenhouse.io/twitch/jobs/8917377002"><img src="x" alt="Apply"/></a> | 3d |\n'
          '| <a href="https://t.com"><strong>Tower</strong></a> | Quant Dev Intern | Chicago, IL +1 | '
          '<a href="https://www.tower-research.com/open-positions/?gh_jid=8044334"><img/></a> | 115d |')
    a, b = parse_rows(md)
    assert (a["company"], a["title"], a["salary"], a["age"]) == ("Twitch", "Software Engineer I", "$193k/yr", "3d")
    assert a["url"] == "https://job-boards.greenhouse.io/twitch/jobs/8917377002"
    assert b["salary"] is None and b["url"].endswith("gh_jid=8044334")


def test_consider_flight_data():
    page = ('<script>self.__next_f.push([1,"{\\"initialData\\":{\\"jobs\\":[{\\"id\\":\\"a1\\",\\"title\\":\\"SWE\\",'
            '\\"apply_url\\":\\"https://x.com/1\\"}]}}"])</script>')
    assert parse_jobs(page) == [{"id": "a1", "title": "SWE", "apply_url": "https://x.com/1"}]


def test_company_key():
    assert company_key("Meta Platforms, Inc.") == company_key("meta platforms") == "metaplatforms"
    assert company_key("Hudson River Trading (HRT)") == "hudsonrivertradinghrt"


# ── routing by tier ───────────────────────────────────────────────────────
def _pipe(tmp_path, conns, **raw):
    s = Settings(raw={"alerts": {"bootstrap_alert_hours": 48, "route_by": "tier"},
                      "eligibility": {"citizenship_filter": True}, **raw},
                 relevance=RelevancePrefs(), connectors=conns, intervals={},
                 directory={"tiktok": ("tiktok", "big_tech")})
    db = Store(tmp_path / "t.db")
    return Pipeline(s, db, http=None), db


def test_feed_only_company_routes_to_its_tier_and_unknown_to_other(tmp_path):
    sim = Fake("simplify", "new-grad", [
        job(source_job_id="a", company="TikTok", company_id=None, title="Software Engineer, New Grad",
            url="https://lifeattiktok.com/search/1", description=None),
        job(source_job_id="b", company="Tiny Startup", company_id=None, title="Software Engineer, New Grad",
            url="https://tiny.example/jobs/2", description=None),
    ])
    pipe, db = _pipe(tmp_path, [sim])
    asyncio.run(pipe.run_source(sim))
    got = dict(db.all("SELECT c.company, a.channel FROM alerts a JOIN canonical_jobs c ON c.id=a.canonical_job_id"))
    assert got == {"TikTok": "big_tech", "Tiny Startup": "other"}
    assert db.one("SELECT tier FROM canonical_jobs WHERE company='TikTok'")[0] == "big_tech"


def test_too_many_years_and_contract_are_dropped(tmp_path):
    gh = Fake("greenhouse", "anthropic", [
        job(source_job_id="1", title="Software Engineer I", description="Requirements:\n- 4+ years of experience in Go"),
        job(source_job_id="2", url="https://job-boards.greenhouse.io/anthropic/jobs/2", title="Software Engineer I",
            description="This is a 6-month contract role."),
        job(source_job_id="3", url="https://job-boards.greenhouse.io/anthropic/jobs/3", title="Software Engineer Intern",
            description="Requirements:\n- 4+ years of experience in Go"),     # interns skip the years rule
    ])
    pipe, db = _pipe(tmp_path, [gh], filters={"max_years_required": 2, "years_action": "drop"})
    asyncio.run(pipe.run_source(gh))
    reasons = dict(db.all("SELECT title || '#' || id, reason FROM canonical_jobs"))
    assert reasons["Software Engineer I#1"].startswith("requires 4+ years")
    assert reasons["Software Engineer I#2"] == "contract: contract role"
    assert db.one("SELECT COUNT(*) FROM alerts")[0] == 1


def test_too_many_years_only_flags_by_default(tmp_path):
    gh = Fake("greenhouse", "anthropic", [
        job(title="Software Engineer I", description="Requirements:\n- 4+ years of experience in Go")])
    pipe, db = _pipe(tmp_path, [gh], filters={"max_years_required": 2})
    asyncio.run(pipe.run_source(gh))
    assert db.one("SELECT COUNT(*) FROM alerts")[0] == 1
    assert "asks for 4+ years of experience" in db.one("SELECT flags FROM canonical_jobs")[0]


def test_jobright_rows():
    from jobalerts.connectors.markdown_list import parse_jobright_rows, _posted
    md = """| Company | Job Title | Location | Work Model | Date Posted |
| ----- | --------- |  --------- | ---- | ------- |
| **[Paychex](https://www.paychex.com/)** | **[Software Engineer I](https://jobright.ai/jobs/info/aaa?utm_source=1103)** | St. Petersburg, FL, United States | Hybrid | Nov 16 |
| ↳ | **[Software Engineer I](https://jobright.ai/jobs/info/bbb?utm_source=1103)** | Cincinnati, OH, United States | Remote | Nov 15 |
| **[Zoox](https://www.zoox.com/)** | **[Software Intern [Summer 2027]](https://jobright.ai/jobs/info/ccc)** | Foster City, CA, United States | On Site | Nov 16 |
"""
    rows = parse_jobright_rows(md)
    assert [(r["company"], r["title"]) for r in rows] == [
        ("Paychex", "Software Engineer I"), ("Zoox", "Software Intern [Summer 2027]")]
    assert rows[0]["location"] == "St. Petersburg, FL, United States; Cincinnati, OH, United States"
    assert rows[0]["url"] == "https://jobright.ai/jobs/info/aaa?utm_source=1103"
    assert _posted("Nov 16").month == 11
