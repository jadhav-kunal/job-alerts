#!/usr/bin/env python3
import json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
UA="job-alerts-research/0.1 (personal internship monitor)"
S=requests.Session(); S.headers.update({"User-Agent":UA}); TO=12

MISSING = {
 "Meta":["meta","metacareers"],"Microsoft":["microsoft"],"Google":["google"],"Apple":["apple"],
 "Amazon":["amazon"],"NVIDIA":["nvidia","nvidiacorp"],"TikTok":["tiktok","tiktokglobal"],
 "Tesla":["tesla","teslamotors"],"Salesforce":["salesforce"],"Intuit":["intuit"],
 "Hudson River Trading":["hudsonrivertrading","hrtcareers","wehearthrt","hudson-river-trading"],
 "OpenAI":["openai"],"Perplexity AI":["perplexityai","perplexity"],
 "Cognition AI":["cognition","cognitionai","cognitionlabs"],"Databricks":["databricks"],
 "Anduril":["anduril","andurilindustries"],"SpaceX":["spacex","spaceexplorationtechnologies"],
 "Netflix":["netflix"],"Snowflake":["snowflake","snowflakecomputing"],
 "Datadog":["datadog","datadoghq"],"MongoDB":["mongodb","mongodbinc"],
 "Kraken":["kraken","payward","krakenfx","krakendigitalassetexchange"],
 "Mistral":["mistralai","mistral"],"Cohere":["cohere","cohereai","coherehealth"],
 "ElevenLabs":["elevenlabs","elevenlabsio"],"Harvey":["harvey","harveyai"],
 "Cursor":["anysphere","cursor"],"Replit":["replit"],"Wiz":["wiz","wizio","wizinc"],
 "Snyk":["snyk"],"1Password":["1password","agilebits","1passwordcareers"],
 "Vanta":["vanta","vantasecurity"],"Zoox":["zoox"],"Shield AI":["shieldai","shield-ai"],
 "Cisco":["cisco"],"IBM":["ibm"],"Okta":["okta","oktainc"],"HubSpot":["hubspot"],
 "Notion":["notion","notionhq","notionlabs"],"Loom":["loom","useloom"],
 "Linear":["linear","linearapp"],"Benchling":["benchling"],"Hinge Health":["hingehealth"],
 "Deel":["deel"],"Supabase":["supabase"],"Bolt":["bolt","boltcom","boltfinancial","boltapp"],
 "Sardine":["sardine","sardineai"],"Superhuman":["superhuman"],"Plaid":["plaid"],
 "Ramp":["ramp","rampcom","ramponline"],
}

def g(url):
    try:
        r=S.get(url,timeout=TO,allow_redirects=True); return r.status_code, r.text[:300000]
    except Exception as e: return None, f"ERR{type(e).__name__}"

def check(c,s):
    out=[]
    for name,url,test in [
      ("greenhouse",f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",lambda b:len(json.loads(b).get("jobs",[]))),
      ("greenhouse-embed",f"https://job-boards.greenhouse.io/embed/job_board?for={s}",lambda b: 1 if 'opening' in b else 0),
      ("lever",f"https://api.lever.co/v0/postings/{s}?mode=json",lambda b:len(json.loads(b))),
      ("ashby",f"https://api.ashbyhq.com/posting-api/job-board/{s}",lambda b:len(json.loads(b).get("jobs",[]))),
      ("smartrecruiters",f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=5",lambda b:json.loads(b).get("totalFound",0)),
      ("workable",f"https://apply.workable.com/api/v1/widget/accounts/{s}?details=true",lambda b:len(json.loads(b).get("jobs",[]))),
      ("rippling",f"https://api.rippling.com/platform/api/ats/v1/board/{s}/jobs",lambda b:len(json.loads(b))),
      ("recruitee",f"https://{s}.recruitee.com/api/offers/",lambda b:len(json.loads(b).get("offers",[]))),
      ("jobvite",f"https://jobs.jobvite.com/api/v1/jobs?companyId={s}",lambda b: 1 if 'requisition' in b.lower() else 0),
      ("eightfold",f"https://{s}.eightfold.ai/api/apply/v2/jobs?start=0&num=5&domain={s}.com",lambda b:json.loads(b).get("count",0)),
      ("teamtailor",f"https://{s}.teamtailor.com/jobs.json",lambda b:len(json.loads(b))),
    ]:
        sc,b=g(url)
        if sc==200:
            try:
                n=test(b)
                if n and n>0: out.append((name,s,int(n),url))
            except Exception: pass
    return out

res={}
with ThreadPoolExecutor(max_workers=8) as ex:
    fut={ex.submit(check,c,s):(c,s) for c,ss in MISSING.items() for s in ss}
    for f in as_completed(fut):
        c,s=fut[f]
        try: h=f.result()
        except Exception: h=[]
        if h: res.setdefault(c,[]).extend(h)
for c in sorted(res):
    for ats,slug,n,url in res[c]:
        print(f"{c:22s} {ats:18s} {slug:26s} n={n}")
print("\nHITS:",len(res),"of",len(MISSING))
print("STILL MISSING:", sorted(set(MISSING)-set(res)))
