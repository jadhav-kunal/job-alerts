#!/usr/bin/env python3
import json,requests
from concurrent.futures import ThreadPoolExecutor, as_completed
S=requests.Session(); S.headers.update({"User-Agent":"job-alerts-research/0.1"})
CAND=[
("1Password","ashby","1password"),("Cognition AI","ashby","cognition"),("Cohere","ashby","cohere"),
("Kraken","ashby","kraken.com"),("Kraken","ashby","kraken"),("Linear","ashby","Linear"),("Linear","ashby","linear"),
("Mistral","ashby","mistral.ai"),("Mistral","ashby","mistral"),("Notion","ashby","notion"),
("Replit","ashby","replit"),("Supabase","ashby","supabase"),("Vanta","ashby","vanta"),
("Sentry","ashby","sentry"),("Snowflake","ashby","snowflake"),("Hinge Health","ashby","hinge-health"),
("Palantir","lever","palantir"),("Shield AI","lever","shieldai"),
("Hudson River Trading","greenhouse","hrttalentcommunity"),("Superhuman","greenhouse","grammarly"),
("Figma","greenhouse","figma"),("Hightouch","greenhouse","hightouch"),("Together AI","greenhouse","togetherai"),
("Netflix","eightfold","netflix"),
# extra guesses for the -none- set
("Anduril","greenhouse","andurilindustries"),("SpaceX","greenhouse","spacex"),
("Databricks","greenhouse","databricks"),("Datadog","greenhouse","datadog"),
("MongoDB","greenhouse","mongodb"),("Okta","greenhouse","okta"),("HubSpot","greenhouse","hubspot"),
("Wiz","greenhouse","wizinc"),("Instacart","greenhouse","instacart"),("Airtable","greenhouse","airtable"),
("Benchling","greenhouse","benchling"),("Plaid","greenhouse","plaid"),("Ramp","ashby","ramp"),
("Ramp","greenhouse","ramp"),("Deel","ashby","deel"),("Deel","greenhouse","deel"),
("ElevenLabs","ashby","elevenlabs"),("Harvey","ashby","harvey"),("Cursor","ashby","cursor"),
("Cursor","ashby","anysphere"),("Sardine","ashby","sardine"),("Sardine","greenhouse","sardine"),
("Watershed","ashby","watershed"),("Watershed","greenhouse","watershed"),
("Snyk","greenhouse","snyk"),("Snyk","ashby","snyk"),("Zoox","greenhouse","zoox"),("Zoox","ashby","zoox"),
("Waymo","greenhouse","waymo"),("Optiver","greenhouse","optiverus"),("Jane Street","greenhouse","janestreet"),
("Bolt","greenhouse","bolt"),("Bolt","ashby","bolt"),("PocketFM","lever","pocketfm"),
("Neon","ashby","neon"),("Neon","lever","neon"),
]
def u(ats,s):
    return {"ashby":f"https://api.ashbyhq.com/posting-api/job-board/{s}?includeCompensation=true",
            "lever":f"https://api.lever.co/v0/postings/{s}?mode=json",
            "greenhouse":f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
            "eightfold":f"https://{s}.eightfold.ai/api/apply/v2/jobs?start=0&num=1&domain={s}.com"}[ats]
def go(c,ats,s):
    try:
        r=S.get(u(ats,s),timeout=15)
        if r.status_code!=200: return c,ats,s,r.status_code,0,""
        d=r.json()
        if ats=="lever": n=len(d); t=d[0]["text"] if n else ""
        elif ats=="greenhouse": j=d.get("jobs",[]); n=len(j); t=j[0]["title"] if j else ""
        elif ats=="eightfold": n=d.get("count",0); t=(d.get("positions") or [{}])[0].get("name","")
        else: j=d.get("jobs",[]); n=len(j); t=j[0]["title"] if j else ""
        return c,ats,s,200,n,t
    except Exception as e: return c,ats,s,None,0,f"ERR {type(e).__name__}"
rows=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    fut=[ex.submit(go,*x) for x in CAND]
    for f in as_completed(fut): rows.append(f.result())
for c,ats,s,sc,n,t in sorted(rows):
    flag="OK " if n>0 else "   "
    print(f"{flag}{c:22s} {ats:12s} {s:22s} http={sc} n={n:5d} {t[:45]}")
