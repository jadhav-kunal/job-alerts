import pytest

from jobalerts.models import NormalizedJob
from jobalerts.relevance import RelevancePrefs, classify

PREFS = RelevancePrefs(seasons={"Spring 2027", "Summer 2027", "Fall 2027", "Winter 2027"})


def run(title, loc=("San Francisco, CA",), **kw):
    return classify(NormalizedJob(source="t:x", source_job_id="1", company=kw.pop("company", "Acme"), title=title,
                                  url="https://x", locations=list(loc), **kw), PREFS)


@pytest.mark.parametrize("title,level,cat", [
    ("Software Engineer Intern", "intern", "software"),
    ("Software Engineer Intern - AI Infrastructure (Summer 2027)", "intern", "ai_ml"),
    ("Machine Learning Engineer, New Grad 2027", "new_grad", "ai_ml"),
    ("Research Scientist Intern, LLM Post-Training", "intern", "research"),
    ("Research Engineer Intern", "intern", "research"),
    ("PhD Research Intern - Computer Vision", "intern", "research"),
    ("Software Development Engineer I", "new_grad", "software"),
    ("SWE, University Grad", "new_grad", "software"),
    ("Data Scientist Intern", "intern", "data"),
    ("Quantitative Developer Intern", "intern", "quant"),
    ("Backend Engineer - Early Career", "new_grad", "software"),
    ("AI Resident", "new_grad", "ai_ml"),
    ("Anthropic Fellows Program, AI Safety", "new_grad", "ai_ml"),
    ("Software Engineering Co-op (Fall 2027)", "intern", "software"),
    ("Associate Software Engineer", "new_grad", "software"),
    ("Junior Full Stack Developer", "new_grad", "software"),
])
def test_accepts(title, level, cat):
    d = run(title)
    assert d.accept, d.reason
    assert (d.level, d.category) == (level, cat)


@pytest.mark.parametrize("title", [
    "Senior Software Engineer",
    "Staff Machine Learning Engineer",
    "Research Scientist",                         # unlevelled mid-level — off by default
    "Campus Recruiter",
    "Head of Early Career Recruiting",
    "Bastrop Campus Planning Manager",
    "Sensor Placement and Analysis Engineer",
    "Mechanical Engineering Intern",
    "Electrical Engineer Intern - Avionics",
    "Marketing Intern",
    "Sales Development Intern",
    "UX Research Intern",
    "Market Research Intern",
    "Finance Intern",
    "Software Engineer Intern (Summer 2025)",     # stale
    "Software Engineering Intern, Summer 2026",   # season not wanted
    "Director of Engineering",
    "Software Engineer II",
    "Quantitative Trader Intern",
    "Cloud & AI Finance Intern",
    "Engineer I, Electromechanical",
])
def test_rejects(title):
    assert not run(title).accept


def test_roblox_senior_plus_early_career_is_kept_with_flag():
    d = run("[2026] Senior Machine Learning Engineer - PhD Early Career")
    assert d.accept and d.flags


def test_simplify_level_hint_and_terms():
    assert run("Software Engineer", level_hint="new_grad").accept
    assert not run("Software Engineer Intern", terms=["Summer 2026"]).accept
    assert run("Software Engineer Intern", terms=["Summer 2027"]).accept
    assert not run("Hardware Engineer Intern", level_hint="intern", category_hint="Hardware").accept
    assert not run("Product Manager Intern", level_hint="intern", category_hint="Product").accept


@pytest.mark.parametrize("loc,ok", [
    (["London, UK"], False), (["Bangalore, IN"], False), (["Toronto, ON, Canada"], False),
    (["Remote - US"], True), (["Remote"], True), (["US, WA, Seattle"], True), (["US-CA-Santa-Clara"], True),
    (["New York, NY", "London, UK"], True), (["Austin, TX"], True), ([], True), (["Washington, Bellevue"], True),
])
def test_locations(loc, ok):
    assert run("Software Engineer Intern", loc=loc).accept is ok


def test_description_early_career_signal():
    assert run("Software Engineer", description="We want recent graduates with 0-2 years of experience").accept
    assert not run("Software Engineer", description="5+ years of experience").accept


@pytest.mark.parametrize("title,phd", [
    ("Machine Learning PhD Intern", True),
    ("Software Engineer Intern (Ph.D.)", True),
    ("PhD Resident, AI", True),
    ("Research Scientist, New Grad - PhD", True),
    ("ML Intern - Masters/PhD", False),
    ("Research Intern (MS or PhD)", False),
    ("R&D Intern - Master's/PhD", False),
    ("2027 Summer Intern, MS/PhD, Software Engineer", False),
    ("Software Engineer, New Grad", False),
])
def test_phd_only_titles(title, phd):
    d = classify(NormalizedJob(source="t:x", source_job_id="1", company="Acme", title=title, url="https://x",
                               locations=["New York, NY"]), RelevancePrefs())
    assert d.accept and d.phd_only is phd


def test_phd_only_drop_and_route():
    from jobalerts.config import Settings
    job = NormalizedJob(source="t:x", source_job_id="1", company="Acme", title="Machine Learning PhD Intern",
                        url="https://x", locations=["New York, NY"])
    assert classify(job, RelevancePrefs(phd_only="drop")).reason == "PhD only"
    s = Settings.__new__(Settings)
    s.raw = {"roles": {"phd_only": "route"}, "alerts": {"route_by": "tier"}}
    assert s.route_for("tier1", "intern", True) == "phd" and s.route_for("tier1", "intern", False) == "tier1"
    s.raw["roles"]["phd_only"] = "keep"
    assert s.route_for("tier1", "intern", True) == "tier1"
