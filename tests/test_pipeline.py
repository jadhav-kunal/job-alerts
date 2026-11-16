import asyncio
from datetime import datetime, timedelta, timezone

from jobalerts.config import Settings
from jobalerts.connectors import Connector, FetchResult
from jobalerts.db import Store
from jobalerts.models import NormalizedJob
from jobalerts.pipeline import Pipeline
from jobalerts.relevance import RelevancePrefs

NOW = datetime.now(timezone.utc)


class Fake(Connector):
    def __init__(self, kind, slug, jobs):
        super().__init__(kind=kind, slug=slug, company="Anthropic", company_id="anthropic", tier="tier1")
        self.jobs = jobs

    async def fetch(self, http, etag):
        return FetchResult([NormalizedJob(**{**j, "source": self.key}) for j in self.jobs], None)


def job(**kw):
    base = dict(source="", source_job_id="1", company="Anthropic", company_id="anthropic",
                title="Software Engineer Intern", url="https://job-boards.greenhouse.io/anthropic/jobs/111",
                locations=["San Francisco, CA"], posted_at=NOW, description="Build things.")
    return {**base, **kw}


def make(tmp_path, conns):
    s = Settings(raw={"alerts": {"bootstrap_alert_hours": 48}, "eligibility": {"citizenship_filter": True}},
                 relevance=RelevancePrefs(), connectors=conns, intervals={})
    db = Store(tmp_path / "t.db")
    return Pipeline(s, db, http=None), db


def alerts(db):
    return db.one("SELECT COUNT(*) FROM alerts WHERE alert_type='new'")[0]


def test_same_job_from_two_sources_alerts_once(tmp_path):
    gh = Fake("greenhouse", "anthropic", [job()])
    sim = Fake("simplify", "internships", [job(source_job_id="uuid-1",
                                               url="https://boards.greenhouse.io/anthropic/jobs/111?gh_src=simplify",
                                               description=None, level_hint="intern")])
    pipe, db = make(tmp_path, [gh, sim])
    for c in (gh, sim, gh, sim):             # repeated runs must stay idempotent
        asyncio.run(pipe.run_source(c))
    assert db.one("SELECT COUNT(*) FROM canonical_jobs")[0] == 1
    assert db.one("SELECT COUNT(*) FROM job_sources")[0] == 2
    assert alerts(db) == 1


def test_distinct_requisitions_never_merge(tmp_path):
    gh = Fake("greenhouse", "anthropic", [job(), job(source_job_id="2", url="https://job-boards.greenhouse.io/anthropic/jobs/222",
                                                 title="Software Engineer Intern")])
    pipe, db = make(tmp_path, [gh])
    asyncio.run(pipe.run_source(gh))
    assert alerts(db) == 2


def test_bootstrap_skips_old_jobs(tmp_path):
    old = NOW - timedelta(days=10)
    gh = Fake("greenhouse", "anthropic", [job(posted_at=old)])
    pipe, db = make(tmp_path, [gh])
    asyncio.run(pipe.run_source(gh))
    assert alerts(db) == 0
    gh.jobs.append(job(source_job_id="3", url="https://job-boards.greenhouse.io/anthropic/jobs/333", posted_at=old))
    asyncio.run(pipe.run_source(gh))            # after seeding, anything unseen alerts regardless of age
    assert alerts(db) == 1


def test_citizenship_required_is_dropped(tmp_path):
    gh = Fake("greenhouse", "anthropic", [job(description="Applicants must be a U.S. citizen.")])
    pipe, db = make(tmp_path, [gh])
    asyncio.run(pipe.run_source(gh))
    assert alerts(db) == 0
    assert db.one("SELECT reason FROM canonical_jobs")[0].startswith("requires US citizenship")
