#!/usr/bin/env python3
import re,json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA})
PAT=[("greenhouse",r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_\-]+)"),
     ("greenhouse",r"greenhouse\.io/embed/job_board\?for=([a-z0-9_\-]+)"),
     ("greenhouse",r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9_\-]+)"),
     ("lever",r"jobs\.lever\.co/([a-z0-9_\-]+)"),
     ("lever",r"api\.lever\.co/v0/postings/([a-z0-9_\-]+)"),
     ("ashby",r"jobs\.ashbyhq\.com/([a-zA-Z0-9_\-\.]+)"),
     ("ashby",r"ashbyhq\.com/posting-api/job-board/([a-zA-Z0-9_\-\.]+)"),
     ("ashby",r'"?(?:jobBoardName|organizationSlug|boardName)"?\s*[:=]\s*"([a-zA-Z0-9_\-\.]+)"'),
     ("smartrecruiters",r"smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_\-]+)"),
     ("workday",r"https?://([a-z0-9\-]+)\.(wd\d+)\.myworkdayjobs\.com/([A-Za-z0-9_\-]+)"),
     ("eightfold",r"https?://([a-z0-9\-]+)\.eightfold\.ai"),
     ("phenom",r"([a-z0-9\-]+)\.phenompeople\.com"),
     ("icims",r"([a-z0-9\-]+)\.icims\.com"),
     ("rippling",r"ats\.rippling\.com/([a-zA-Z0-9_\-]+)"),
]
URLS={
"1Password":"https://1password.com/careers","Cognition AI":"https://cognition.com/careers",
"Cohere":"https://cohere.com/careers","Kraken":"https://www.kraken.com/careers",
"Linear":"https://linear.app/careers","Mistral":"https://mistral.ai/careers/",
"Notion":"https://www.notion.com/careers","Replit":"https://replit.com/careers",
"Supabase":"https://supabase.com/careers","Vanta":"https://www.vanta.com/company/careers",
"Sentry":"https://sentry.io/careers/","Snowflake":"https://careers.snowflake.com/us/en/search-results",
"Hinge Health":"https://jobs.ashbyhq.com/hinge-health","Palantir":"https://www.palantir.com/careers/",
"Shield AI":"https://shield.ai/careers/","Hudson River Trading":"https://www.hudsonrivertrading.com/careers/",
"Superhuman":"https://superhuman.com/company/careers","Cisco":"https://careers.cisco.com/global/en",
"Microsoft":"https://apply.careers.microsoft.com/careers","Netflix":"https://explore.jobs.netflix.net/careers",
"NVIDIA":"https://www.nvidia.com/en-us/about-nvidia/careers/","Hightouch":"https://hightouch.com/careers",
"Wiz":"https://www.wiz.io/careers","Snyk":"https://snyk.io/careers/","Zoox":"https://zoox.com/careers",
"Databricks":"https://www.databricks.com/company/careers/open-positions",
"Datadog":"https://careers.datadoghq.com/all-jobs/","MongoDB":"https://www.mongodb.com/company/careers/teams/engineering",
"Okta":"https://www.okta.com/company/careers/","HubSpot":"https://www.hubspot.com/careers/jobs",
"Anduril":"https://www.anduril.com/careers/","SpaceX":"https://www.spacex.com/careers/jobs/",
"Deel":"https://www.deel.com/careers/","Benchling":"https://www.benchling.com/careers",
"ElevenLabs":"https://elevenlabs.io/careers","Harvey":"https://www.harvey.ai/careers",
"Cursor":"https://cursor.com/careers","Plaid":"https://plaid.com/careers/","Ramp":"https://ramp.com/careers",
"Sardine":"https://www.sardine.ai/careers","Together AI":"https://www.together.ai/careers",
"Watershed":"https://watershed.com/careers","Salesforce":"https://careers.salesforce.com/en/jobs/",
"Intuit":"https://jobs.intuit.com/search-jobs","IBM":"https://www.ibm.com/careers/search",
"Tesla":"https://www.tesla.com/careers/search/","Optiver":"https://www.optiver.com/join-us/jobs/",
"Jane Street":"https://www.janestreet.com/join-jane-street/open-roles/",
"Waymo":"https://careers.withwaymo.com","PocketFM":"https://pocketfm.com/careers",
"Bolt":"https://www.bolt.com/careers","Instacart":"https://instacart.careers/current-openings/",
"Airtable":"https://www.airtable.com/careers","Figma":"https://www.figma.com/careers/",
}
def go(c,u):
    try:
        r=S.get(u,timeout=20,allow_redirects=True); b=r.text[:800000]; fin=r.url; sc=r.status_code
    except Exception as e: return c,None,f"ERR {type(e).__name__}",""
    found={}
    for ats,p in PAT:
        for m in re.finditer(p,b):
            g=m.groups()
            v="/".join(x for x in g if x)
            if v.lower() in ("embed","job_board","www","jobs","api","v1","companies","static","assets"): continue
            found.setdefault(ats,set()).add(v)
    s="; ".join(f"{k}={sorted(v)[:3]}" for k,v in found.items())
    return c,sc,s or "-none-",fin
rows=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    fut={ex.submit(go,c,u):c for c,u in URLS.items()}
    for f in as_completed(fut): rows.append(f.result())
for c,sc,s,fin in sorted(rows):
    print(f"{c:22s} {str(sc):5s} {s[:120]}")
