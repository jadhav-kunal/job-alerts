#!/usr/bin/env python3
import requests,re,json
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA})
CAND={"Benchling":["benchling"],"Deel":["deel","deelinc"],"Plaid":["plaid","plaidinc","plaidtechnologies"],
"Snyk":["snyk","snykltd"],"Zoox":["zoox","zooxinc"],"Bolt":["bolt","boltfinancial","boltcom"],
"HubSpot":["hubspot"],"Superhuman":["grammarly","superhuman"],"Discord":["discord"],
"OpenAI":["openai"],"Perplexity AI":["perplexityai","perplexity"],"Cursor":["cursor","anysphere"],
"Salesforce":["salesforce"],"Tesla":["tesla"],"Apple":["apple"],"Zoox2":["zoox"],
"Databricks":["databricks"],"MongoDB":["mongodb"],"Okta":["okta"],"Datadog":["datadog"],
"IBM":["ibm"],"Cisco":["cisco"]}
def t(u):
    try:
        r=S.get(u,timeout=15,allow_redirects=True); return r.status_code,len(r.content),r.url
    except Exception as e: return None,0,f"ERR{type(e).__name__}"
def go(c,s):
    out=[]
    for lbl,u in [("gh-html",f"https://job-boards.greenhouse.io/{s}"),
                  ("ashby-html",f"https://jobs.ashbyhq.com/{s}"),
                  ("lever-html",f"https://jobs.lever.co/{s}")]:
        sc,ln,fin=t(u)
        if sc==200 and ln>3000: out.append(f"{lbl}:{s}(len={ln})")
    return c,out
rows=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    fut=[ex.submit(go,c,s) for c,ss in CAND.items() for s in ss]
    for f in as_completed(fut):
        c,o=f.result()
        if o: rows.append((c,o))
agg={}
for c,o in rows: agg.setdefault(c,[]).extend(o)
for c in sorted(agg): print(f"{c:16s} {'; '.join(agg[c])}")
