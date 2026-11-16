#!/usr/bin/env python3
"""Probe public ATS endpoints for candidate company slugs. Read-only GETs, low rate."""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

UA = "job-alerts-research/0.1 (personal internship monitor)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json,text/html;q=0.8"})
TO = 12

COMPANIES = {
 # name: [candidate slugs]
 "Meta": ["meta","facebook"], "Microsoft": ["microsoft"], "Google": ["google"],
 "Apple": ["apple"], "Amazon": ["amazon"], "NVIDIA": ["nvidia"],
 "ByteDance": ["bytedance"], "TikTok": ["tiktok"], "Tesla": ["tesla"],
 "Rippling": ["rippling"], "Salesforce": ["salesforce"], "Intuit": ["intuit"],
 "Jane Street": ["janestreet","jane-street"], "Hudson River Trading": ["hudsonrivertrading","hrt","wehearthrt"],
 "Optiver": ["optiver","optiverus"], "Anthropic": ["anthropic"], "OpenAI": ["openai"],
 "xAI": ["xai","x-ai"], "Perplexity AI": ["perplexity","perplexityai"],
 "Cognition AI": ["cognition","cognitionai","cognition-ai"], "Scale AI": ["scaleai","scale","scale-ai"],
 "Stripe": ["stripe"], "Palantir": ["palantir","palantirtechnologies"], "Databricks": ["databricks"],
 "Anduril": ["anduril","andurilindustries"], "Waymo": ["waymo"], "SpaceX": ["spacex"],
 "Airbnb": ["airbnb"], "Figma": ["figma"], "Discord": ["discord"], "Roblox": ["roblox"],
 "Netflix": ["netflix"], "Lyft": ["lyft"], "Reddit": ["reddit"], "Pinterest": ["pinterest"],
 "Dropbox": ["dropbox"], "Snowflake": ["snowflake","snowflakecomputing"], "Datadog": ["datadog","datadoghq"],
 "Cloudflare": ["cloudflare"], "MongoDB": ["mongodb"], "Confluent": ["confluent"],
 "Elastic": ["elastic"], "Sentry": ["sentry","getsentry"], "Vercel": ["vercel"],
 "Robinhood": ["robinhood"], "Brex": ["brex"], "Ramp": ["ramp"], "Chime": ["chime"],
 "Affirm": ["affirm"], "Plaid": ["plaid"], "Kraken": ["kraken","krakendigitalassetexchange","payward"],
 "Mistral": ["mistral","mistralai"], "Cohere": ["cohere"], "ElevenLabs": ["elevenlabs"],
 "Runway ML": ["runway","runwayml"], "Modal Labs": ["modal","modallabs"],
 "Together AI": ["together","togetherai"], "Harvey": ["harvey","harveyai"],
 "Cursor": ["cursor","anysphere"], "Replit": ["replit"], "Wiz": ["wiz","wizio"],
 "Snyk": ["snyk"], "1Password": ["1password","agilebits"], "Vanta": ["vanta"],
 "Zoox": ["zoox"], "Shield AI": ["shieldai","shield-ai"], "Cisco": ["cisco"], "IBM": ["ibm"],
 "PocketFM": ["pocketfm","pocket-fm"],
 "Duolingo": ["duolingo"], "Instacart": ["instacart","maplebear"], "Samsara": ["samsara"],
 "Verkada": ["verkada"], "Okta": ["okta"], "PagerDuty": ["pagerduty"], "HubSpot": ["hubspot"],
 "Asana": ["asana"], "Airtable": ["airtable"], "Box": ["box","boxinc"], "Twilio": ["twilio"],
 "GitLab": ["gitlab"], "Checkr": ["checkr"], "Gusto": ["gusto"], "Toast": ["toast","toasttab"],
 "Peloton": ["peloton","pelotoncycle","onepeloton"], "Doximity": ["doximity"], "Lattice": ["lattice","latticehq"],
 "Amplitude": ["amplitude"], "Mixpanel": ["mixpanel"], "SendBird": ["sendbird"],
 "Fivetran": ["fivetran"], "Temporal": ["temporal","temporalio","temporaltechnologies"],
 "Descript": ["descript"], "Flatiron Health": ["flatironhealth","flatiron"],
 "LaunchDarkly": ["launchdarkly"], "Hightouch": ["hightouch"], "Mercury": ["mercury","mercurytechnologies"],
 "Pendo": ["pendo","pendoio"], "Faire": ["faire","fairewholesale"], "Airbyte": ["airbyte"],
 "Notion": ["notion"], "Loom": ["loom"], "Linear": ["linear"], "Benchling": ["benchling"],
 "Hinge Health": ["hingehealth"], "Alchemy": ["alchemy"], "PostHog": ["posthog"],
 "Deel": ["deel"], "Watershed": ["watershed","watershedclimate"], "Neon": ["neon","neondatabase"],
 "Supabase": ["supabase"], "Bolt": ["bolt","boltcom"], "Sardine": ["sardine","sardineai"],
 "Superhuman": ["superhuman"],
}

def probe(url, expect="json"):
    try:
        r = S.get(url, timeout=TO, allow_redirects=True)
        return r.status_code, r.text[:400000], r.url
    except Exception as e:
        return None, f"ERR {type(e).__name__}", url

def check(company, slug):
    out = []
    # Greenhouse (classic board API)
    sc, body, _ = probe(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if sc == 200:
        try:
            d = json.loads(body); n = len(d.get("jobs", []))
            if n > 0: out.append(("greenhouse", slug, n, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"))
        except Exception: pass
    # Lever
    sc, body, _ = probe(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if sc == 200:
        try:
            d = json.loads(body)
            if isinstance(d, list) and len(d) > 0: out.append(("lever", slug, len(d), f"https://api.lever.co/v0/postings/{slug}?mode=json"))
        except Exception: pass
    # Ashby
    sc, body, _ = probe(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if sc == 200:
        try:
            d = json.loads(body); n = len(d.get("jobs", []))
            if n > 0: out.append(("ashby", slug, n, f"https://api.ashbyhq.com/posting-api/job-board/{slug}"))
        except Exception: pass
    # SmartRecruiters
    sc, body, _ = probe(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=10")
    if sc == 200:
        try:
            d = json.loads(body); n = d.get("totalFound", 0)
            if n and n > 0: out.append(("smartrecruiters", slug, n, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"))
        except Exception: pass
    # Workable
    sc, body, _ = probe(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    if sc == 200 and '"jobs"' in body:
        try:
            d = json.loads(body); n = len(d.get("jobs", []))
            if n > 0: out.append(("workable", slug, n, f"https://apply.workable.com/api/v1/widget/accounts/{slug}"))
        except Exception: pass
    # Rippling ATS board
    sc, body, _ = probe(f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs")
    if sc == 200:
        try:
            d = json.loads(body)
            if isinstance(d, list) and len(d) > 0: out.append(("rippling", slug, len(d), f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"))
        except Exception: pass
    return out

results = {}
tasks = []
with ThreadPoolExecutor(max_workers=8) as ex:
    fut = {}
    for c, slugs in COMPANIES.items():
        for s in slugs:
            fut[ex.submit(check, c, s)] = (c, s)
    for f in as_completed(fut):
        c, s = fut[f]
        try:
            hits = f.result()
        except Exception as e:
            hits = []
        if hits:
            results.setdefault(c, []).extend(hits)

print(json.dumps(results, indent=1, sort_keys=True))
