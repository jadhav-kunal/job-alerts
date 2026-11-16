from jobalerts import citizenship
from jobalerts.normalize import ats_identity, normalize_url


def test_greenhouse_hosts_collapse():
    a = normalize_url("https://boards.greenhouse.io/anthropic/jobs/5391376008?gh_src=abc&utm_source=x")
    b = normalize_url("https://job-boards.greenhouse.io/anthropic/jobs/5391376008/")
    assert a == b


def test_apply_suffix_and_workday_locale():
    assert normalize_url("https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3/application") == \
        normalize_url("https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3")
    assert normalize_url("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/X_JR1") == \
        normalize_url("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/X_JR1")


def test_ats_identity():
    assert ats_identity("https://job-boards.greenhouse.io/anthropic/jobs/5391376008") == ("greenhouse", "anthropic", "5391376008")
    assert ats_identity("https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c/apply")[0] == "lever"
    assert ats_identity("https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3")[2].startswith("8fb1615c")
    assert ats_identity("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/China-Shanghai/Custom-SOC-Intern---2027_JR2024692") == \
        ("workday", "nvidia", "JR2024692")
    assert ats_identity("https://www.amazon.jobs/en/jobs/3120598/software-dev") == ("amazon", "amazon", "3120598")


def test_citizenship_tiers():
    assert citizenship.check("Applicants must be a U.S. citizen due to contract requirements.").status == "reject"
    assert citizenship.check("Must be able to obtain and maintain a Secret security clearance.").status == "reject"
    assert citizenship.check("Active TS/SCI clearance required.").status == "reject"
    assert citizenship.check("This role may involve access to technology subject to export control (EAR).").status == "warn"
    assert citizenship.check("Build great ML systems with us.").status == "ok"
    assert citizenship.check(None).status == "unknown"
    assert citizenship.check(None, "U.S. Citizenship is Required").status == "reject"
    r = citizenship.check("We are unable to offer visa sponsorship for this role.")
    assert r.status == "ok" and r.no_sponsorship


def test_custom_domain_greenhouse_urls_stay_distinct():
    assert normalize_url("https://instacart.careers/job/?gh_jid=1") != normalize_url("https://instacart.careers/job/?gh_jid=2")
    assert ats_identity("https://instacart.careers/job/?gh_jid=6819435") == ("greenhouse", "instacart.careers", "6819435")


def test_clearance_in_title():
    assert citizenship.check(None, title="Software Engineer - Cleared").status == "reject"
    assert citizenship.check(None, title="Software Engineer, TS/SCI").status == "reject"
    assert citizenship.check(None, title="Security Software Engineer Intern").status == "unknown"
