#!/usr/bin/env python3
import json,requests
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA,"Accept":"application/json,text/plain,*/*"})
TESTS=[
("Amazon","GET","https://www.amazon.jobs/en/search.json?base_query=software+engineer+intern&result_limit=5",None),
("Apple-api","POST","https://jobs.apple.com/api/role/search",{"query":"intern","filters":{},"page":1}),
("Microsoft","GET","https://gcsservices.careers.microsoft.com/search/api/v1/search?q=intern&l=en_us&pg=1&pgSz=5&o=Relevance&flt=true",None),
("Tesla","GET","https://www.tesla.com/cua-api/apps/careers/state",None),
("Google","GET","https://careers.google.com/api/v3/search/?q=intern",None),
("Meta-gql","GET","https://www.metacareers.com/jobs",None),
("TikTok","GET","https://lifeattiktok.com/api/v1/search/job/posts?keyword=intern&limit=5",None),
("ByteDance","GET","https://jobs.bytedance.com/api/v1/search/job/posts?keyword=intern&limit=5",None),
("NVIDIA-wd","POST","https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",{"appliedFacets":{},"limit":5,"offset":0,"searchText":"intern"}),
("Salesforce","GET","https://careers.salesforce.com/en/jobs/?search=intern&pagesize=5",None),
("Intuit","GET","https://jobs.intuit.com/search-jobs/results?ActiveFacetID=0&CurrentPage=1&RecordsPerPage=5&Distance=50&SearchResultsModuleName=Search+Results&SearchFiltersModuleName=Search+Filters&SearchType=5&keyword=intern",None),
("IBM","GET","https://www-api.ibm.com/search/api/v2?q=intern",None),
("Cisco","GET","https://jobs.cisco.com/jobs/SearchJobs/intern?listFilterMode=1&projectOffset=0",None),
("OpenAI","GET","https://openai.com/careers/search/",None),
("Perplexity","GET","https://job-boards.greenhouse.io/perplexity",None),
("Snyk","GET","https://snyk.io/careers/",None),
("Zoox","GET","https://zoox.com/careers/",None),
("Plaid","GET","https://plaid.com/careers/openings/",None),
("Deel","GET","https://www.deel.com/careers/",None),
("Benchling","GET","https://www.benchling.com/careers",None),
("Superhuman","GET","https://www.grammarly.com/careers/jobs",None),
("HubSpot","GET","https://www.hubspot.com/careers/jobs",None),
("SpaceX-gh","GET","https://boards-api.greenhouse.io/v1/boards/spacex/jobs?content=true",None),
]
def go(n,m,u,body):
    try:
        r=S.post(u,json=body,timeout=20) if m=="POST" else S.get(u,timeout=20)
        ct=r.headers.get("content-type","")[:40]
        prev=""
        if "json" in ct:
            try:
                d=r.json()
                prev=json.dumps(d)[:180]
            except Exception: prev=r.text[:150]
        else: prev=r.text[:150].replace("\n"," ")
        return n,r.status_code,ct,len(r.content),prev
    except Exception as e: return n,None,"",0,f"ERR {type(e).__name__}: {str(e)[:80]}"
rows=[]
with ThreadPoolExecutor(max_workers=6) as ex:
    fut=[ex.submit(go,*t) for t in TESTS]
    for f in as_completed(fut): rows.append(f.result())
for n,sc,ct,ln,p in sorted(rows):
    print(f"=== {n} http={sc} ct={ct} len={ln}\n    {p}\n")
