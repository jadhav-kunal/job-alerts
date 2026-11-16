#!/usr/bin/env python3
import requests, re
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA})
SITES=["https://www.linkedin.com/robots.txt","https://www.indeed.com/robots.txt",
"https://joinhandshake.com/robots.txt","https://simplify.jobs/robots.txt",
"https://jobright.ai/robots.txt","https://github.com/robots.txt",
"https://boards.greenhouse.io/robots.txt","https://job-boards.greenhouse.io/robots.txt",
"https://jobs.lever.co/robots.txt","https://jobs.ashbyhq.com/robots.txt",
"https://www.myworkdayjobs.com/robots.txt","https://nvidia.wd5.myworkdayjobs.com/robots.txt",
"https://jobs.smartrecruiters.com/robots.txt","https://www.amazon.jobs/robots.txt",
"https://jobs.apple.com/robots.txt","https://www.metacareers.com/robots.txt",
"https://jobs.careers.microsoft.com/robots.txt","https://www.tesla.com/robots.txt",
"https://openai.com/robots.txt","https://www.google.com/about/careers/robots.txt",
"https://careers.google.com/robots.txt","https://lifeattiktok.com/robots.txt",
"https://api.greenhouse.io/robots.txt","https://www.glassdoor.com/robots.txt",
"https://www.ziprecruiter.com/robots.txt","https://raw.githubusercontent.com/robots.txt",
]
def go(u):
    try:
        r=S.get(u,timeout=15)
        return u,r.status_code,r.text[:2500]
    except Exception as e: return u,None,f"ERR {type(e).__name__}"
rows=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    fut=[ex.submit(go,u) for u in SITES]
    for f in as_completed(fut): rows.append(f.result())
for u,sc,t in sorted(rows):
    print("="*90); print(f"{u}  [http={sc}]")
    # condense: show User-agent blocks mentioning * and any /job path rules
    lines=[l.rstrip() for l in t.splitlines()]
    out=[];cur=None;keep=False
    for l in lines:
        ll=l.lower().strip()
        if ll.startswith("user-agent:"):
            keep = ("*" in ll)
            cur=l
            if keep: out.append(l)
        elif keep and (ll.startswith("disallow")or ll.startswith("allow")or ll.startswith("crawl-delay")):
            out.append(l)
    print("\n".join(out[:60]) if out else t[:600])
