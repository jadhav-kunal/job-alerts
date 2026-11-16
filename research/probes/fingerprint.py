#!/usr/bin/env python3
import re,sys,json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
SIG=[("greenhouse",r"(boards|job-boards)\.greenhouse\.io|greenhouse\.io/embed|grnh\.se"),
("lever",r"jobs\.lever\.co|api\.lever\.co|lever-client"),
("ashby",r"jobs\.ashbyhq\.com|ashbyhq\.com/posting-api|_ashby"),
("workday",r"myworkdayjobs\.com|workday\.com/.*careers|wd\d+\.myworkday"),
("smartrecruiters",r"smartrecruiters\.com|jobs\.smartrecruiters"),
("icims",r"icims\.com"),("jobvite",r"jobvite\.com"),("workable",r"workable\.com"),
("eightfold",r"eightfold\.ai"),("phenom",r"phenompeople\.com|phenom\.com"),
("avature",r"avature\.net"),("successfactors",r"successfactors\.(com|eu)|sapsf\.com"),
("oracle-taleo",r"taleo\.net|oraclecloud\.com/hcmUI|oracle\.com/.*recruit"),
("rippling",r"ats\.rippling\.com|rippling\.com/platform/api/ats"),
("bamboohr",r"bamboohr\.com"),("teamtailor",r"teamtailor\.com"),
("recruitee",r"recruitee\.com"),("breezy",r"breezy\.hr"),
("paylocity",r"paylocity\.com"),("dayforce",r"dayforcehcm\.com"),
("jobsapi/jibe",r"jibeapply\.com|jobs\.jobvite|jobsapi"),
("custom-nextjs",r"__NEXT_DATA__"),
]
URLS={
"Amazon":["https://www.amazon.jobs/en/search?base_query=intern"],
"Apple":["https://jobs.apple.com/en-us/search"],
"Microsoft":["https://jobs.careers.microsoft.com/global/en/search"],
"Google":["https://www.google.com/about/careers/applications/jobs/results/"],
"Meta":["https://www.metacareers.com/jobs"],
"NVIDIA":["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite","https://www.nvidia.com/en-us/about-nvidia/careers/"],
"TikTok":["https://lifeattiktok.com/search","https://careers.tiktok.com/position"],
"Tesla":["https://www.tesla.com/careers/search/"],
"Salesforce":["https://careers.salesforce.com/en/jobs/"],
"Intuit":["https://jobs.intuit.com/search-jobs"],
"Cisco":["https://jobs.cisco.com/jobs/SearchJobs"],
"IBM":["https://www.ibm.com/careers/search"],
"Snowflake":["https://careers.snowflake.com/us/en/search-results"],
"Snyk":["https://snyk.io/careers/"],
"OpenAI":["https://openai.com/careers/search/"],
"Perplexity AI":["https://www.perplexity.ai/hub/careers","https://job-boards.greenhouse.io/perplexityai"],
"Cursor":["https://cursor.com/careers","https://anysphere.inc/careers"],
"Mistral":["https://mistral.ai/careers"],
"ElevenLabs":["https://elevenlabs.io/careers"],
"Harvey":["https://www.harvey.ai/careers"],
"Notion":["https://www.notion.com/careers","https://www.notion.so/careers"],
"Linear":["https://linear.app/careers"],
"Loom":["https://www.loom.com/careers"],
"Replit":["https://replit.com/careers"],
"Supabase":["https://supabase.com/careers"],
"Vanta":["https://www.vanta.com/company/careers"],
"Deel":["https://www.deel.com/careers/"],
"Benchling":["https://www.benchling.com/careers"],
"Hinge Health":["https://www.hingehealth.com/careers/"],
"Plaid":["https://plaid.com/careers/"],
"Ramp":["https://ramp.com/careers"],
"Kraken":["https://www.kraken.com/careers"],
"Zoox":["https://zoox.com/careers"],
"Shield AI":["https://shield.ai/careers/"],
"1Password":["https://1password.com/careers"],
"Sardine":["https://www.sardine.ai/careers"],
"Superhuman":["https://superhuman.com/careers"],
"Bolt":["https://www.bolt.com/careers"],
"Hudson River Trading":["https://www.hudsonrivertrading.com/careers/"],
"Cognition AI":["https://cognition.ai/careers"],
"Anduril":["https://www.anduril.com/careers/"],
"SpaceX":["https://www.spacex.com/careers/jobs/"],
"Netflix":["https://explore.jobs.netflix.net/careers"],
"Databricks":["https://www.databricks.com/company/careers/open-positions"],
"Datadog":["https://careers.datadoghq.com/all-jobs/"],
"MongoDB":["https://www.mongodb.com/company/careers/teams/engineering"],
"Okta":["https://www.okta.com/company/careers/"],
"HubSpot":["https://www.hubspot.com/careers/jobs"],
"Cohere":["https://cohere.com/careers"],
"Wiz":["https://www.wiz.io/careers"],
"Palantir":["https://www.palantir.com/careers/"],
"Waymo":["https://waymo.com/careers/"],
"Optiver":["https://optiver.com/working-at-optiver/career-opportunities/"],
"Jane Street":["https://www.janestreet.com/join-jane-street/open-roles/"],
"Together AI":["https://www.together.ai/careers"],
"Neon":["https://neon.com/careers"],
"Watershed":["https://watershed.com/careers"],
"Hightouch":["https://hightouch.com/careers"],
"PocketFM":["https://pocketfm.com/careers"],
"Sentry":["https://sentry.io/careers/"],
}
def fp(c,url):
    try:
        r=S.get(url,timeout=20,allow_redirects=True)
        body=r.text[:600000]; final=r.url; sc=r.status_code
    except Exception as e:
        return c,url,None,f"ERR {type(e).__name__}",""
    hits=[n for n,p in SIG if re.search(p,body,re.I) or re.search(p,final,re.I)]
    return c,url,sc,",".join(hits) or "-none-",final
rows=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    fut={ex.submit(fp,c,u):(c,u) for c,us in URLS.items() for u in us}
    for f in as_completed(fut): rows.append(f.result())
for c,u,sc,h,final in sorted(rows):
    print(f"{c:22s} {str(sc):5s} {h[:70]:70s} {final[:80]}")
