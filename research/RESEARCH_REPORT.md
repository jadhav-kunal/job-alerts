# 2027 Internship Job Monitor — Research Report & Implementation Plan

**Date:** 2026-08-20  **Status:** Research complete — no production code written yet.
**Method:** 114 target companies were probed directly against live ATS endpoints from this machine
(~600 HTTP requests). Every claim below is tagged **Verified** (I ran it), **Likely** (strong
indirect evidence), or **Uncertain** (needs a human check).

---

## 1. Executive Summary

**In plain English:** you do not need 114 scrapers, and you should not scrape LinkedIn or Indeed at all.

Three facts, all verified by direct probing, determine the whole design:

1. **Three ATS platforms cover 81% of your list.** Greenhouse (59 companies), Ashby (29), and Lever (4)
   all expose *unauthenticated, documented, public JSON APIs*. Add Workday, Eightfold, Rippling and
   Amazon's public JSON endpoint and you reach **86% of your 114 companies through 7 generic connectors.**

2. **The companies you cannot reach directly are exactly the ones the GitHub lists cover.**
   Apple, Google, Meta, Tesla, TikTok, ByteDance and Microsoft all block or JS-render their career
   sites. All seven appear with active listings in `SimplifyJobs/Summer2027-Internships`. The GitHub
   feed is not a nice-to-have; it is the coverage layer for Big Tech.

3. **`SimplifyJobs/Summer2027-Internships` ships a structured JSON file, not just a README.**
   `.github/scripts/listings.json` on the `dev` branch is a 10.8 MB array of 14,452 records with
   `title`, `company_name`, `locations[]`, `terms[]`, `date_posted`, `active`, `sponsorship`, and
   critically a `url` that points **directly at the company's ATS**. This makes cross-source
   deduplication a deterministic URL match rather than a fuzzy-text problem.

**The strategy:** poll ~100 public ATS JSON APIs on a schedule, poll three GitHub repos for the
companies you can't reach, deduplicate primarily on normalized application URL and ATS-native job ID,
filter with deterministic title rules (which resolve 98.4% of titles — measured on a real 7,260-title
corpus), and send one email per canonical job. Run it as a single Python process on a $5/month VPS.

**What you should not build:** a LinkedIn scraper, an Indeed scraper, a Handshake integration, a
CAPTCHA/anti-bot bypass layer, or an embeddings pipeline. Each is either legally hostile, technically
unstable, or solves a problem you don't have.

---

## 2. Feasibility Assessment

| Dimension | Score | Justification |
|---|---|---|
| Company career pages | **8.5/10** | 98/114 reachable via public APIs today (verified). The 16 misses are structural, not effort-limited. |
| Job boards | **3/10** | LinkedIn, Indeed, Handshake and Jobright are all effectively closed. Simplify is open *via GitHub*, not via its site. |
| GitHub lists | **9.5/10** | Structured JSON, ETag-cached, 30-min cadence, direct ATS URLs, `active` lifecycle flag. Near-ideal source. |
| Deduplication | **8.5/10** | Solvable deterministically because the GitHub feed carries ATS URLs. Would be ~5/10 if it only had company+title. |
| Automation | **9/10** | Stateless polling + conditional GETs; no auth, no browsers, no proxies. |
| **Overall** | **8/10** | Very feasible with the scope trimmed to legitimate sources. |

**Why not 10:** Big Tech (Apple/Google/Meta/Tesla/TikTok) is permanently second-hand via GitHub feeds,
so those alerts lag by up to 30 minutes and depend on a third party's uptime. And 6 companies
(Snyk, Deel, Bolt, HubSpot, Cisco, IBM) currently have **no legitimate machine-readable route at all**.

---

## 3. Company → ATS Mapping

Legend — **Difficulty:** ⬤ trivial (public JSON) · ◐ moderate (POST/parse) · ○ hard/blocked.
Job counts are live totals I retrieved, proving the endpoint returns real data.

### 3.1 Big Tech

| Company | ATS / Platform | Endpoint or Career URL | API/Feed | Jobs seen | Diff. | Recommended Method | Status |
|---|---|---|---|---|---|---|---|
| Amazon | Custom JSON | `www.amazon.jobs/en/search.json` | Public JSON | 21 | ⬤ | Direct JSON connector | **Verified** |
| NVIDIA | Workday | `nvidia.wd5.myworkdayjobs.com` / `NVIDIAExternalCareerSite` | CXS POST | 954 | ◐ | WorkdayConnector | **Verified** |
| Salesforce | Workday | `salesforce.wd12` / `External_Career_Site` | CXS POST | 771 | ◐ | WorkdayConnector | **Verified** |
| Rippling | Rippling ATS | `api.rippling.com/platform/api/ats/v1/board/rippling/jobs` | Public JSON | 748 | ⬤ | RipplingConnector | **Verified** |
| Netflix | Eightfold | `explore.jobs.netflix.net` | `apply/v2/jobs` | 508 | ◐ | EightfoldConnector | **Verified** |
| Intuit | TalentBrew | `jobs.intuit.com/search-jobs/results` | JSON+HTML | — | ◐ | Custom connector (V2) | **Verified** reachable |
| Microsoft | Eightfold | `apply.careers.microsoft.com` | — | — | ◐ | EightfoldConnector; else GitHub feed | **Likely** |
| Google | Custom SPA | `google.com/about/careers` | none | — | ○ | **GitHub feed only** | **Verified** blocked |
| Apple | Custom API | `jobs.apple.com/api/v1/search` → HTTP 401 | auth required | — | ○ | **GitHub feed only** | **Verified** blocked |
| Meta | Custom SPA | `metacareers.com` → HTTP 400 | none | — | ○ | **GitHub feed only** | **Verified** blocked |
| TikTok | Custom API | `lifeattiktok.com` → HTTP 405 | none | — | ○ | **GitHub feed only** (159 active) | **Verified** blocked |
| ByteDance | Custom SPA | `jobs.bytedance.com` | none | — | ○ | **GitHub feed only** (90 active) | **Verified** blocked |
| Tesla | Akamai-protected | 403 on *everything*, incl. `robots.txt` | none | — | ○ | **Do not scrape.** GitHub feed only | **Verified** blocked |

### 3.2 Tier 1

| Company | ATS | Slug | Jobs | Diff. | Method | Status |
|---|---|---|---|---|---|---|
| Anthropic | Greenhouse | `anthropic` | 494 | ⬤ | GreenhouseConnector | **Verified** |
| OpenAI | Ashby | `openai` | 741 | ⬤ | AshbyConnector | **Verified** |
| Stripe | Greenhouse | `stripe` | 569 | ⬤ | GreenhouseConnector | **Verified** |
| Databricks | Greenhouse | `databricks` | 810 | ⬤ | GreenhouseConnector | **Verified** |
| Anduril | Greenhouse | `andurilindustries` | 2237 | ⬤ | GreenhouseConnector | **Verified** |
| SpaceX | Greenhouse | `spacex` | 2170 | ⬤ | GreenhouseConnector ⚠ 24MB w/ content | **Verified** |
| Waymo | Greenhouse | `waymo` | 368 | ⬤ | GreenhouseConnector | **Verified** |
| Scale AI | Greenhouse | `scaleai` | 208 | ⬤ | GreenhouseConnector | **Verified** |
| xAI | Greenhouse | `xai` | 260 | ⬤ | GreenhouseConnector | **Verified** |
| Jane Street | Greenhouse | `janestreet` | 233 | ⬤ | GreenhouseConnector | **Verified** |
| Optiver | Greenhouse | `optiverus` | 178 | ⬤ | GreenhouseConnector (US board) | **Verified** |
| Palantir | Lever | `palantir` | 308 | ⬤ | LeverConnector | **Verified** |
| Perplexity AI | Ashby | `perplexity` | 100 | ⬤ | AshbyConnector | **Verified** |
| Cognition AI | Ashby | `cognition` | 83 | ⬤ | AshbyConnector | **Verified** |
| Hudson River Trading | Greenhouse | `hrttalentcommunity` | 3 | ◐ | **Partial** — board holds only "Campus Talent Community"; real roles on own site | **Verified partial** |

### 3.3 Tier 2

| Company | ATS | Slug | Jobs | Method | Status |
|---|---|---|---|---|---|
| Snowflake | Ashby | `snowflake` | 389 | AshbyConnector (Phenom is only the search UI) | **Verified** |
| Harvey | Ashby | `harvey` | 369 | AshbyConnector | **Verified** |
| ElevenLabs | Ashby | `elevenlabs` | 255 | AshbyConnector | **Verified** |
| Mistral | Ashby | `mistral.ai` | 164 | AshbyConnector — slug is a domain | **Verified** |
| Cohere | Ashby | `cohere` | 151 | ⚠ *not* `greenhouse/coherehealth` (different company) | **Verified** |
| Ramp | Ashby | `ramp` | 136 | AshbyConnector | **Verified** |
| Cursor | Ashby | `cursor` | 115 | AshbyConnector (entity = Anysphere) | **Verified** |
| Plaid | Ashby | `plaid` | 107 | AshbyConnector | **Verified** |
| Vanta | Ashby | `vanta` | 97 | AshbyConnector | **Verified** |
| Kraken | Ashby | `kraken.com` | 90 | AshbyConnector — slug is a domain | **Verified** |
| Replit | Ashby | `replit` | 74 | AshbyConnector | **Verified** |
| 1Password | Ashby | `1password` | 64 | AshbyConnector | **Verified** |
| Sentry | Ashby | `sentry` | 38 | ⚠ also a 3-job Rippling board; Ashby authoritative | **Verified** |
| Modal Labs | Ashby | `modal` | 31 | AshbyConnector | **Verified** |
| Confluent | Ashby | `confluent` | 30 | AshbyConnector | **Verified** |
| Runway ML | Ashby | `runway` | 4 | AshbyConnector | **Verified** |
| Datadog | Greenhouse | `datadog` | 442 | GreenhouseConnector | **Verified** |
| MongoDB | Greenhouse | `mongodb` | 406 | GreenhouseConnector | **Verified** |
| Cloudflare | Greenhouse | `cloudflare` | 306 | GreenhouseConnector | **Verified** |
| Brex | Greenhouse | `brex` | 294 | GreenhouseConnector | **Verified** |
| Elastic | Greenhouse | `elastic` | 249 | GreenhouseConnector | **Verified** |
| Roblox | Greenhouse | `roblox` | 229 | GreenhouseConnector | **Verified** |
| Pinterest | Greenhouse | `pinterest` | 220 | GreenhouseConnector | **Verified** |
| Affirm | Greenhouse | `affirm` | 204 | GreenhouseConnector | **Verified** |
| Airbnb | Greenhouse | `airbnb` | 191 | GreenhouseConnector | **Verified** |
| Figma | Greenhouse | `figma` | 161 | GreenhouseConnector | **Verified** |
| Lyft | Greenhouse | `lyft` | 161 | GreenhouseConnector | **Verified** |
| Reddit | Greenhouse | `reddit` | 148 | GreenhouseConnector | **Verified** |
| Robinhood | Greenhouse | `robinhood` | 126 | GreenhouseConnector | **Verified** |
| Wiz | Greenhouse | `wizinc` | 120 | GreenhouseConnector | **Verified** |
| Vercel | Greenhouse | `vercel` | 84 | GreenhouseConnector | **Verified** |
| Together AI | Greenhouse | `togetherai` | 64 | ⚠ also 22-job SmartRecruiters board | **Verified** |
| Chime | Greenhouse | `chime` | 58 | GreenhouseConnector | **Verified** |
| Discord | Greenhouse | `discord` | 53 | GreenhouseConnector | **Verified** |
| Dropbox | Greenhouse | `dropbox` | 43 | GreenhouseConnector | **Verified** |
| Shield AI | Lever | `shieldai` | 431 | LeverConnector | **Verified** |
| Zoox | Lever | `zoox` | 237 | LeverConnector | **Verified** |
| PocketFM | Lever | `pocketfm` | 1 | LeverConnector (very low volume) | **Verified** |
| Snyk | Ashby | `snyk` | **0** | ❌ Board exists, API returns `jobs:[]`. **Gap** | **Verified no-API** |
| Cisco | Phenom | `careers.cisco.com` | — | ❌ No public API found; 0 active in feed. **Gap** | **Uncertain** |
| IBM | Custom SPA | `ibm.com/careers` | — | ❌ No public API found; 0 active in feed. **Gap** | **Uncertain** |

### 3.4 Tier 3

| Company | ATS | Slug | Jobs | Status |
|---|---|---|---|---|
| Okta | Greenhouse | `okta` | 334 | **Verified** |
| Toast | Greenhouse | `toast` | 323 | **Verified** |
| Verkada | Greenhouse | `verkada` | 280 | **Verified** |
| Samsara | Greenhouse | `samsara` | 263 | **Verified** |
| Fivetran | Greenhouse | `fivetran` | 243 | **Verified** |
| GitLab | Greenhouse | `gitlab` | 206 | **Verified** |
| Twilio | Greenhouse | `twilio` | 146 | **Verified** |
| Asana | Greenhouse | `asana` | 126 | **Verified** |
| Box | Greenhouse | `boxinc` | 126 | **Verified** — slug is `boxinc` |
| Instacart | Greenhouse | `instacart` | 118 | **Verified** |
| Gusto | Greenhouse | `gusto` | 93 | **Verified** |
| Mixpanel | Greenhouse | `mixpanel` | 92 | **Verified** |
| Hightouch | Greenhouse | `hightouch` | 72 | **Verified** |
| Duolingo | Greenhouse | `duolingo` | 67 | **Verified** |
| Faire | Greenhouse | `faire` | 63 | **Verified** |
| Mercury | Greenhouse | `mercury` | 56 | **Verified** |
| Temporal | Greenhouse | `temporaltechnologies` | 53 | **Verified** |
| Peloton | Greenhouse | `peloton` | 52 | **Verified** |
| LaunchDarkly | Greenhouse | `launchdarkly` | 50 | **Verified** |
| Checkr | Greenhouse | `checkr` | 42 | **Verified** |
| Pendo | Greenhouse | `pendo` | 40 | **Verified** |
| Amplitude | Greenhouse | `amplitude` | 34 | **Verified** |
| Flatiron Health | Greenhouse | `flatironhealth` | 33 | **Verified** |
| PagerDuty | Greenhouse | `pagerduty` | 29 | **Verified** |
| Airtable | Greenhouse | `airtable` | 16 | **Verified** |
| SendBird | Greenhouse | `sendbird` | 11 | **Verified** |
| Doximity | Greenhouse | `doximity` | 10 | **Verified** |
| Lattice | Greenhouse | `lattice` | 9 | **Verified** |
| Descript | Greenhouse | `descript` | 7 | **Verified** |
| Notion | Ashby | `notion` | 128 | **Verified** |
| Hinge Health | Ashby | `hinge-health` | 71 | **Verified** |
| Supabase | Ashby | `supabase` | 56 | **Verified** |
| Benchling | Ashby | `benchling` | 50 | **Verified** |
| Sardine | Ashby | `sardine` | 35 | **Verified** |
| Watershed | Ashby | `watershed` | 33 | **Verified** — ⚠ *not* `greenhouse/watershed` (different co.) |
| Linear | Ashby | `Linear` | 32 | **Verified** — slugs case-insensitive |
| Alchemy | Ashby | `alchemy` | 17 | **Verified** |
| PostHog | Ashby | `posthog` | 12 | **Verified** |
| Airbyte | Ashby | `airbyte` | 10 | **Verified** |
| HubSpot | Greenhouse | `hubspot` | **0** | ❌ Board returns 0 jobs. **Gap** |
| Deel | Ashby | `Deel` | **0** | ❌ API returns `jobs:[]`. **Gap** |
| Bolt | Ashby | `bolt` | **0** | ❌ API returns `jobs:[]`. **Gap** |
| **Loom** | — | — | — | 🔄 **Acquired by Atlassian** — `loom.com/careers` 301s to `atlassian.com`. Drop or retarget. |
| **Neon** | — | — | — | 🔄 **Acquired by Databricks** — `neon.com/careers` 301s to `databricks.com`. Already covered. |
| **Superhuman** | — | — | — | 🔄 **Acquired by Grammarly** — career page embeds Greenhouse slug `grammarly`. Retarget. |

### 3.5 Coverage Summary

```
Total targets                              114
Reachable via a connector today             98   (86.0%)
  └─ via GENERIC ATS connectors             96   (84.2%)
       Greenhouse  59 · Ashby 29 · Lever 4 · Workday 2 · Eightfold 1 · Rippling 1
  └─ via custom connectors                   2   (Amazon JSON, Intuit TalentBrew)
Blocked → GitHub-feed-only                   6   Apple Google Meta Tesla TikTok ByteDance
Acquired / retarget                          3   Loom Neon Superhuman
No legitimate route (true gaps)              6   Snyk Deel Bolt HubSpot Cisco IBM
Likely-but-unverified                        1   Microsoft (Eightfold)

★ Greenhouse + Ashby + Lever alone = 92 companies = 80.7% of the list.
```

---

## 4. Source-by-Source Job Board Analysis

### 4.1 LinkedIn — 🔴 DO NOT SCRAPE

| Field | Finding |
|---|---|
| Official API? | Yes, but partner-gated (Talent Solutions). Not available to individuals. |
| Public structured data? | No. |
| Scraping allowed? | **Explicitly forbidden.** |
| Technical difficulty | Very high (auth walls, bot detection, rate limits). |
| Reliability | Poor. |
| **Recommended** | **Do not integrate.** |
| Fallback | None needed — company ATS + GitHub feeds already cover these jobs. |
| Risk | **High (legal, not just technical).** |

**Verified** — `linkedin.com/robots.txt` opens with:
> "The use of robots or other automated means to access LinkedIn without the express permission of
> LinkedIn is strictly prohibited."

This is not a grey area. And the case law cuts against you on the part that matters: in *hiQ Labs v.
LinkedIn*, the Ninth Circuit held the **CFAA** doesn't bar scraping public data — but the district
court then granted LinkedIn summary judgment on **breach of contract**, and hiQ settled with a
**$500,000 judgment** in Dec 2022. "Not a federal crime" ≠ "allowed." Skip it.

### 4.2 Indeed — 🔴 DO NOT SCRAPE

| Field | Finding |
|---|---|
| Official API? | **Discontinued.** Publisher API shut down in 2023; no self-serve replacement. |
| Public structured data? | No. |
| Scraping allowed? | robots.txt permits some paths but **disallows `/graphql` and `/api/*`** — i.e. exactly the data endpoints. ToS prohibits scraping. |
| Technical difficulty | High — Cloudflare + bot detection. |
| **Recommended** | **Do not integrate.** |
| Risk | High. |

**Verified** — `indeed.com/robots.txt` contains `Disallow: /graphql`, `Disallow: /api/getrecjobs`.
Indeed is also an *aggregator* of the same ATS postings you already read at the source, so it adds
duplicates, not coverage.

### 4.3 Handshake — 🔴 NOT VIABLE

| Field | Finding |
|---|---|
| Official API? | **EDU API exists but is restricted to Career Services partners** (institutions), granted via a Handshake Relationship Manager. Not available to students. |
| Public structured data? | No — all job data sits behind student SSO. |
| Scraping allowed? | `app.joinhandshake.com/robots.txt` uses an **allowlist**: `/login`, `/register`, `/employers`, `/jobs/*/share_preview` … Job listings are **not** allowed. |
| **Recommended** | **Do not integrate.** Use the Handshake UI manually. |
| Risk | High — requires authenticating as you and circumventing access controls. |

Note `joinhandshake.com/robots.txt` (marketing site) says `Disallow:` (allow-all), but the marketing
site has no job data. The app subdomain is the restrictive one. **Verified.**

### 4.4 Simplify — 🟢 USE, VIA GITHUB ONLY

| Field | Finding |
|---|---|
| Official API? | Not public. |
| Public structured data? | **Yes — Simplify publishes it themselves** to `SimplifyJobs/Summer2027-Internships`. |
| Scraping allowed? | Don't scrape `simplify.jobs`. You don't need to. |
| **Recommended** | Read `.github/scripts/listings.json` (branch `dev`) via `raw.githubusercontent.com`. |
| Risk | **Low** — it's a public repo the company maintains for this purpose. |

This is the single best non-ATS source available and is covered in §5.

### 4.5 Jobright AI — 🔴 DO NOT SCRAPE

| Field | Finding |
|---|---|
| Official API? | None. |
| Public structured data? | No. |
| Scraping allowed? | `jobright.ai/robots.txt` **allows** `/jobs/*` but **disallows `/api/`, `/api/*`** — the JSON is off-limits. |
| **Recommended** | **Do not integrate.** Its value (AI matching) is a product feature, not a data feed. |
| Risk | Medium-high. |

**Verified.**

### 4.6 GitHub Repositories — 🟢 PRIMARY SOURCE

See §5. **Recommended, highest-value non-ATS source.**

### 4.7 Summary Matrix

| Source | Official API | Public structured data | Scraping OK | Difficulty | Reliability | Recommendation | Risk |
|---|---|---|---|---|---|---|---|
| **Company ATS APIs** | ✅ documented | ✅ JSON | ✅ yes | Low | High | **Build on this** | 🟢 |
| **GitHub lists** | ✅ GitHub REST | ✅ JSON/MD | ✅ yes | Low | High | **Build on this** | 🟢 |
| Simplify (site) | ❌ | via GitHub | ❌ | — | — | Use GitHub instead | 🟢 via GH |
| LinkedIn | Partner-only | ❌ | ❌ **forbidden** | Very high | Low | **Do not use** | 🔴 |
| Indeed | Discontinued | ❌ | ❌ | High | Low | **Do not use** | 🔴 |
| Handshake | Institution-only | ❌ | ❌ | High | Low | **Do not use** | 🔴 |
| Jobright | ❌ | ❌ | ❌ (`/api/` denied) | High | Low | **Do not use** | 🔴 |

---

## 5. GitHub Repository Monitoring

### 5.1 SimplifyJobs/Summer2027-Internships — the crown jewel

**Verified facts** (GitHub REST API + raw fetches, 2026-08-20):

| Property | Value |
|---|---|
| Stars | 46,625 |
| Default branch | **`dev`** (not `main`) |
| Last push | 2026-08-21 (minutes before this research) |
| License | **None** ⚠ (see §13) |
| Repo size | **3.4 GB** — ⚠ never `git clone` this |
| **Structured data** | **`.github/scripts/listings.json`** — 10.8 MB, `dev` branch only (404 on `main`) |
| Update cadence | **Every 30 minutes**, via committed bot updates |
| Records | 14,452 total · **1,901 active+visible** · 522 active with a `Summer 2027` term |

**Record schema** (verified against live data):
```json
{
  "id": "bba5c5b2-6284-4f59-b1f9-478c46f31025",
  "source": "Simplify",
  "company_name": "Samsung Research America",
  "title": "Intern - Robot Intelligence",
  "category": "AI/ML/Data",
  "locations": ["Mountain View, CA"],
  "terms": ["Spring 2026", "Summer 2026", "Fall 2026"],
  "url": "https://job-boards.greenhouse.io/samsungresearchamericainternship/jobs/8348787002",
  "company_url": "https://simplify.jobs/c/Samsung-Research-America",
  "date_posted": 1766543125,
  "date_updated": 1766543125,
  "active": false,
  "is_visible": true,
  "sponsorship": "Other",
  "degrees": []
}
```

**Why this changes the architecture.** The `url` field is the **company's own ATS URL**, not a
Simplify redirect. Distribution of the 14,452 URLs by host:

```
 1237  job-boards.greenhouse.io      252  globalhr.wd5.myworkdayjobs.com
  666  jobs.smartrecruiters.com      180  boards.greenhouse.io
  601  jobs.ashbyhq.com              140  apply.workable.com
  446  jobs.lever.co                 140  jobs.bytedance.com
  287  lifeattiktok.com              113  www.tesla.com
  ...  (Workday tenants, iCIMS, Oracle, Rippling)
```

So a Simplify record for an Anthropic job carries
`https://job-boards.greenhouse.io/anthropic/jobs/5391376008` — the *same URL* your Greenhouse
connector produces. **Cross-source dedup collapses to a normalized-URL equality check.** No
embeddings, no fuzzy matching, for the overwhelming majority of cases.

**Other gifts in this schema:**
- `active` → free lifecycle signal (closed detection without a diffing sweep).
- `date_posted` / `date_updated` (unix) → free new-vs-updated detection.
- `terms[]` → free season filtering (`Summer 2027`).
- `sponsorship` / `degrees[]` → free eligibility filtering.

**How to poll:** conditional GET on
`https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json`.
**Verified:** it returns an `ETag`, and re-requesting with `If-None-Match` returns **HTTP 304, 0 bytes**.
Polling every 15 minutes costs essentially nothing when unchanged.

⚠ **Do not parse the READMEs.** `README.md` is 302 KB and `README-Off-Season.md` is 1.1 MB of HTML-in-
markdown. The JSON is strictly better and is what the READMEs are generated from.

### 5.2 speedyapply/2027-SWE-College-Jobs and 2027-AI-College-Jobs

| Property | SWE repo | AI repo |
|---|---|---|
| Stars | 8,893 | 6,175 |
| Last push | 2026-08-20 | 2026-08-20 |
| License | None ⚠ | None ⚠ |
| Structured JSON? | **No** — data lives in a private Supabase (`SUPABASE_URL`/`SUPABASE_KEY` are Actions secrets) | Same |
| Files | `README.md`, `INTERN_INTL.md`, `NEW_GRAD_USA.md`, `NEW_GRAD_INTL.md` | same |
| **Update cadence** | **Once daily, `cron: '0 12 * * *'`** (verified in `.github/workflows/get-jobs.yml`) | same |

Data format is a markdown table with embedded HTML:
```
| Company | Position | Location | Salary | Posting | Age |
| <a href="https://www.nvidia.com"><strong>NVIDIA</strong></a> | NVIDIA Spring 2027 Internships: … |
  Santa Clara, CA | $62/hr | <a href="https://nvidia.wd5.myworkdayjobs.com/…">…</a> | … |
```

**Value added over Simplify:** it carries **salary** (`$62/hr`), which Simplify's JSON does not, and
it splits USA vs INTL and INTERN vs NEW_GRAD into separate files — cheap pre-filtering.

**How to poll:** conditional GET the four `.md` files per repo; parse the table rows with a regex for
the `<a href>` in the Company and Posting columns. **Poll once daily at ~12:15 UTC** — polling more
often is pure waste, since the source itself only refreshes daily.

### 5.3 Detecting additions, updates and deletions

| Repo | New job | Updated job | Deleted/closed job |
|---|---|---|---|
| Simplify | `id` unseen | `date_updated` increased | `active` flips `true→false` |
| speedyapply | Posting URL unseen | Row content hash changed | Row disappears from table |

For speedyapply, deletion requires a **set-difference sweep** guarded by a success check (see §11) —
if a fetch fails or returns a suspiciously short table, do *not* mark everything closed.

### 5.4 Mapping GitHub jobs back to your companies

1. Normalize `company_name` → your `company_id` via an alias table
   (`"Samsung Research America"`, `"Meta"`, `"Facebook"` → canonical id).
2. **Better: match on the URL first.** Parse `job-boards.greenhouse.io/{slug}/jobs/{id}` → you already
   know `slug=anthropic` maps to Anthropic. URL-derived mapping is exact; name matching is fuzzy.
3. Jobs from companies **not** on your list: store them but mark `company_tracked=false`, and only
   alert if a future preference opts them in. Don't throw them away — 727 distinct companies have
   active listings and your target list may grow.

### 5.5 GitHub API rate limits — **Verified, and it bit me during this research**

- **Unauthenticated: 60 requests/hour** (I hit the ceiling mid-research).
- **Authenticated with a PAT: 5,000 requests/hour.**
- `raw.githubusercontent.com` fetches do **not** consume REST quota and support ETags.

**Design rule:** use `raw.githubusercontent.com` + `If-None-Match` for the data files, and reserve
authenticated REST calls for commit-metadata checks. Always ship a PAT.

**Webhooks?** Not available — you can't add a webhook to a repo you don't own. GitHub *does* offer
per-repo Atom feeds (`/commits/dev.atom`), but note `github.com/robots.txt` contains `Disallow: /*.atom$`.
Polling `raw.githubusercontent.com` with ETags is cheaper and unambiguous. **Poll; don't push.**

---

## 6. ATS-Level Connectors — where the abstraction works

### 6.1 Verified connector coverage

| Connector | Access pattern | Auth | Companies | Verified behaviour |
|---|---|---|---|---|
| `GreenhouseConnector` | `GET boards-api.greenhouse.io/v1/boards/{slug}/jobs` | none | **59** | Returns `id`, `updated_at`, `first_published`, `requisition_id`, `absolute_url`, `location.name`, `metadata[]`, `application_deadline`. ETag → 304. |
| `AshbyConnector` | `GET api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | none | **29** | Returns full `descriptionHtml`+`descriptionPlain` **in the list call**, plus `applyUrl`, `jobUrl`, `employmentType`, `department`, `team`, `secondaryLocations[]`, `compensation`, `isListed`. |
| `LeverConnector` | `GET api.lever.co/v0/postings/{slug}?mode=json` | none | **4** | Returns `id`, `text`, `createdAt`, `categories`, `applyUrl`, `hostedUrl`, `workplaceType`, `descriptionPlain`. `robots.txt`: `Allow: /`, `Crawl-delay: 1`. |
| `WorkdayConnector` | `POST {tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | none | **2** | **Verified on 7/7 tenants** (NVIDIA, Salesforce, Intel, Cadence, KLA, Disney, Tencent). Body `{appliedFacets:{},limit,offset,searchText}`. Paginated. |
| `EightfoldConnector` | `GET {org}.eightfold.ai/api/apply/v2/jobs?start&num&domain` | none | **1–2** | Verified on Netflix (508). Microsoft likely. |
| `RipplingConnector` | `GET api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` | none | **1** | Verified (748). |
| `SmartRecruitersConnector` | `GET api.smartrecruiters.com/v1/companies/{slug}/postings` | none | **0 primary** | Works, but ⚠ see §13 — robots.txt disallows all UAs except LinkedInBot. |

### 6.2 The three ATS gotchas I found by probing (each one would have burned you)

**1. Ashby's public API is effectively opt-in.** Four companies (Deel, Snyk, Bolt, Superhuman) have a
live Ashby board at `jobs.ashbyhq.com/{slug}` but the posting API returns **HTTP 200 with `{"jobs": []}`**
— tested in every casing. The board HTML contains a `window.__appData` blob with org metadata but *not*
the postings, which load from an internal endpoint that `jobs.ashbyhq.com/robots.txt` **disallows**
(`Disallow: /api/`). **Board presence ≠ API access, and a 200 does not mean success.**

**2. Slug collisions are real and silently wrong.** Two examples found:
   - `greenhouse/watershed` → a **bioinformatics** company, not Watershed (climate, on Ashby).
   - `lever/neon` → a **Brazilian fintech** (Portuguese job titles), not Neon the database company.
   - `greenhouse/coherehealth` → **Cohere Health**, not Cohere the AI lab.
   Slugs must be validated against the company's own career page, not guessed. My probe would have
   assigned all three wrongly.

**3. Payload sizes vary by 20×.** Anthropic's Greenhouse list is **355 KB**; the same board with
`?content=true` is **7.2 MB**. SpaceX with content is **24 MB**. Never fetch descriptions wholesale —
poll the light list, then fetch content only for job IDs you haven't seen.

### 6.3 Where the abstraction breaks — custom connectors still required

| Company | Why generic fails | Effort |
|---|---|---|
| Amazon | Bespoke `search.json` schema | S — thin JSON connector |
| Intuit | TalentBrew JSON envelope wrapping HTML | M |
| Hudson River Trading | Greenhouse board holds only a "talent community"; real roles elsewhere | M |
| Cisco | Phenom People platform, no documented public API | M–L, uncertain |
| IBM | Custom Next.js SPA | L, uncertain |
| Apple/Google/Meta/Tesla/TikTok/ByteDance | Blocked or auth-walled — **don't build these** | ✗ use GitHub feed |

**Answer to "can most companies be handled by a few connectors?": yes — 84.2% via 7 generic
connectors, and 80.7% via just three (Greenhouse, Ashby, Lever).** Build those three first.

### 6.4 Recommended fallback chain (legitimate options only)

```
1. ATS public JSON API        ← 86% of companies stop here
        ↓ fails / returns 0
2. Simplify listings.json     ← covers Apple, Google, Meta, Tesla, TikTok, ByteDance
        ↓ not present
3. speedyapply markdown tables ← adds salary; daily
        ↓ not present
4. Schema.org JobPosting on the company's own job page (if present)
        ↓ absent
5. Mark source DEGRADED → health alert to you. STOP.
```

There is deliberately **no browser-automation rung**. Every company where a headless browser would be
"needed" is a company that is actively blocking automation (Tesla returns 403 even on `robots.txt`) —
that's a signal to stop, not a puzzle to solve. Playwright stays out of V1 and V2.

---

## 7. Recommended Architecture

```
                          ┌──────────────────────────────────┐
                          │   APScheduler (in-process)       │
                          │   tier-based intervals + jitter  │
                          └───────────────┬──────────────────┘
                                          │  emits FetchTask(source_id)
                          ┌───────────────▼──────────────────┐
                          │   Fetch Worker Pool (asyncio)     │
                          │   httpx · ETag cache · retries    │
                          │   per-host rate limiter           │
                          └───────────────┬──────────────────┘
             ┌────────────────────────────┼────────────────────────────┐
             ▼                            ▼                            ▼
   ┌───────────────────┐      ┌───────────────────────┐    ┌────────────────────┐
   │  ATS CONNECTORS   │      │   GITHUB CONNECTORS   │    │ CUSTOM CONNECTORS  │
   │  greenhouse (59)  │      │  simplify listings    │    │  amazon  (json)    │
   │  ashby      (29)  │      │     .json  (30 min)   │    │  intuit  (tbrew)   │
   │  lever       (4)  │      │  speedyapply SWE (1d) │    │                    │
   │  workday     (2)  │      │  speedyapply AI  (1d) │    │                    │
   │  eightfold   (1)  │      └───────────┬───────────┘    └─────────┬──────────┘
   │  rippling    (1)  │                  │                          │
   └─────────┬─────────┘                  │                          │
             └────────────────────────────┼──────────────────────────┘
                                          ▼
                         ┌────────────────────────────────┐
                         │  RAW INGEST  (raw_payloads)    │   ← store first, parse second
                         │  gzip blob + sha256 + run_id   │      (replayable, debuggable)
                         └───────────────┬────────────────┘
                                         ▼
                         ┌────────────────────────────────┐
                         │  NORMALIZATION                 │
                         │  Pydantic → NormalizedJob       │
                         │  title/location/URL canonical.  │
                         │  ✗ schema violation → quarantine│
                         └───────────────┬────────────────┘
                                         ▼
                         ┌────────────────────────────────┐
                         │  RELEVANCE CLASSIFIER          │   ← BEFORE dedup: 98.4% of rows
                         │  L1 title rules → 98.4%        │      die here, so dedup only ever
                         │  L2 field rules                │      sees ~1.6% of the volume
                         │  L3 LLM (~0.5% of titles)      │
                         └───────────────┬────────────────┘
                                         ▼
                         ┌────────────────────────────────┐
                         │  DEDUPLICATION ENGINE          │
                         │  L0 source id → L1 apply URL   │
                         │  L2 ATS-native id → L3 f'print │
                         │  L4 fuzzy (guarded)            │
                         └───────────────┬────────────────┘
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │  DATABASE   canonical_jobs 1 ──< job_sources  │
                 │             job_events · scraper_runs         │
                 └───────────────┬───────────────────────────────┘
                                 ▼
                 ┌───────────────────────────────────────────────┐
                 │  ALERT OUTBOX  (UNIQUE constraint = idempotency)│
                 │  INSERT ON CONFLICT DO NOTHING                 │
                 └───────────────┬───────────────────────────────┘
                                 ▼
             ┌───────────────────┴──────────────────┐
             ▼                   ▼                  ▼
          Email               Telegram           Discord
        (V1, Resend)          (V1, free)          (V2)

   ┌──────────────────────────────────────────────────────────────┐
   │ OBSERVABILITY: scraper_runs · heartbeat → Healthchecks.io    │
   │ structured JSON logs · daily digest · staleness alerts       │
   └──────────────────────────────────────────────────────────────┘
```

**Two deliberate changes from your draft diagram:**

1. **Relevance runs *before* deduplication, not after.** Measured on a real 7,260-title corpus, title
   rules reject 98.4% of postings. Filtering first means the dedup engine and the database handle
   ~1.6% of the volume. Your draft had dedup first, which would make the expensive stage do 60× more work.

2. **A raw-ingest layer sits before normalization.** Store the raw payload (gzipped, hashed) before
   parsing. When a career site changes shape, you can replay history against the fixed parser instead
   of having permanently lost the data. This is the single highest-leverage resilience decision.

---

## 8. Canonical Job Schema

### 8.1 `NormalizedJob` (what every connector must emit)

| Field | Type | Req? | Notes |
|---|---|---|---|
| `source_id` | str | ✅ | e.g. `greenhouse:anthropic` |
| `source_job_id` | str | ✅ | ATS-native id. Non-negotiable — the dedup backbone. |
| `company_id` | str | ✅ | Resolved via alias table, never raw text |
| `title` | str | ✅ | Verbatim |
| `application_url` | url | ✅ | Normalized (§9.2) |
| `listing_url` | url | ✅ | May equal application_url |
| `locations` | list[Location] | ✅ | Always a list, even for one |
| `posted_at` | datetime | ⬜ | Greenhouse `first_published`, Ashby `publishedAt`, Lever `createdAt` |
| `updated_at` | datetime | ⬜ | **Greenhouse only** (verified 496/496). Ashby/Lever lack it → use hashes |
| `employment_type` | enum | ⬜ | intern / full_time / contract / unknown |
| `department`, `team` | str | ⬜ | Ashby/Lever provide; Greenhouse mostly doesn't |
| `description_html` / `_plain` | str | ⬜ | Ashby gives it free in list; Greenhouse costs 20× |
| `compensation` | obj | ⬜ | Ashby `compensation`; speedyapply salary |
| `remote_type` | enum | ⬜ | onsite / hybrid / remote / unknown |
| `application_deadline` | date | ⬜ | Greenhouse exposes it |
| `raw` | dict | ✅ | Full source payload — always keep |

**Derived / system fields:** `normalized_title`, `normalized_locations[]`, `title_tokens[]`,
`fingerprint` (§9.3), `content_hash`, `description_hash`, `relevance_score`, `match_reasons[]`,
`internship_season`, `experience_level`, `scraper_version`, `first_seen_at`, `last_seen_at`,
`missing_run_count`, `status`.

### 8.2 What to store — and what not to

| Item | Store? | Why |
|---|---|---|
| Raw JSON payload | ✅ **yes**, gzipped | Replay parsers after a site change. Cheap. |
| Raw HTML | ⬜ only on parse failure | Large and rarely useful when JSON exists |
| `content_hash` (whole record) | ✅ yes | Cheap change detection where `updated_at` is absent |
| `description_hash` | ✅ yes | Distinguishes *meaningful* edits from metadata churn |
| Normalized description | ⬜ V2 | Only needed for L4 similarity |
| **Embedding / vector** | ❌ **no** | §9.6 — solves a problem you don't have. Skip in V1 *and* V2. |
| `scraper_version` | ✅ yes | Lets you find "everything parsed by the broken v3 connector" |
| `crawl_timestamp` / `run_id` | ✅ yes | Ties every row to a `scraper_runs` record |

**Required vs optional rule of thumb:** required = anything the dedup engine or the alert needs
(`source_job_id`, `company_id`, `title`, `application_url`, `locations`). Everything else is optional
and must have a sane default — a connector should never fail because a company left `department` blank.

---

## 9. Deduplication Algorithm

### 9.1 The core insight

Because Simplify's `url` field is the company's real ATS URL, the same Anthropic job seen via the
Greenhouse connector and via the GitHub feed produces **the same normalized URL and the same ATS-native
job id**. Dedup is therefore *deterministic* for the overwhelming majority of cases. Fuzzy matching is
a rare fallback, not the main mechanism.

### 9.2 Level 2 — URL normalization (do this first; it powers everything else)

```python
STRIP_PARAMS = {
  "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
  "gh_src","gh_jid","lever-source","source","ref","referrer","trk","trackingId",
  "refId","originalSubdomain","src","from","channel","recruiter","rx_source",
}
def normalize_url(u: str) -> str:
    u = follow_known_redirects(u)              # bounded: max 3 hops, HEAD only
    p = urlsplit(u.strip())
    scheme = "https"
    host   = p.netloc.lower().removeprefix("www.")
    host   = GREENHOUSE_HOST_ALIASES.get(host, host)   # boards. == job-boards.
    path   = p.path.rstrip("/")
    qs     = [(k,v) for k,v in parse_qsl(p.query) if k.lower() not in STRIP_PARAMS]
    return urlunsplit((scheme, host, path, urlencode(sorted(qs)), ""))  # fragment dropped
```
⚠ **Verified necessity:** the feed contains both `boards.greenhouse.io` (180 URLs) and
`job-boards.greenhouse.io` (1,237 URLs) for the same platform. Without host aliasing you will duplicate
every Greenhouse job that arrives from two sources.

### 9.3 Level 3 — ATS-native identity extraction

```python
ATS_ID_PATTERNS = [
 ("greenhouse", r"greenhouse\.io/(?P<org>[\w-]+)/jobs/(?P<id>\d+)"),
 ("ashby",      r"ashbyhq\.com/(?P<org>[\w.\-]+)/(?P<id>[0-9a-f-]{36})"),
 ("lever",      r"jobs\.lever\.co/(?P<org>[\w-]+)/(?P<id>[0-9a-f-]{36})"),
 ("workday",    r"(?P<org>[\w-]+)\.wd\d+\.myworkdayjobs\.com/.*/(?P<id>[\w-]+_[A-Z0-9]+)"),
 ("smartrec",   r"jobs\.smartrecruiters\.com/(?P<org>[\w-]+)/(?P<id>\d+)"),
]
def ats_identity(url):           # → ("greenhouse", "anthropic", "5391376008") or None
    for ats, pat in ATS_ID_PATTERNS:
        if m := re.search(pat, url):
            return ats, m["org"].lower(), m["id"]
    return None
```

### 9.4 The full matching cascade

```python
def resolve_canonical(job: NormalizedJob) -> tuple[CanonicalJob, bool]:
    """Returns (canonical_job, is_new). Cascade stops at the first confident match."""

    # ── L0: same source, same id → we've seen this exact listing before
    if s := db.get_source(job.source_id, job.source_job_id):
        return s.canonical_job, False

    # ── L1: exact normalized application URL  (catches ~all cross-source dupes)
    nurl = normalize_url(job.application_url)
    if c := db.find_by_normalized_url(nurl):
        return c, False

    # ── L2: ATS-native identity  (survives URL formatting drift)
    if ident := ats_identity(job.application_url):
        if c := db.find_by_ats_identity(*ident):
            return c, False

    # ── L3: deterministic fingerprint  (for sources with no usable URL)
    fp = fingerprint(job)
    if c := db.find_by_fingerprint(fp):
        if not _is_distinct_ats_posting(job, c):        # ← SAFETY RULE, see below
            return c, False

    # ── L4: guarded fuzzy match  (last resort, conservative)
    for cand in db.candidates(company_id=job.company_id, within_days=21):
        if _is_distinct_ats_posting(job, cand):
            continue
        if (token_set_ratio(job.normalized_title, cand.normalized_title) >= 92
            and locations_overlap(job.locations, cand.locations)
            and job.employment_type == cand.employment_type):
            return cand, False

    return db.create_canonical(job), True


def _is_distinct_ats_posting(a, b) -> bool:
    """NEVER merge two postings that both carry distinct native ids from the same ATS.
    Two different requisitions ARE two different jobs, however similar the titles look."""
    ia, ib = ats_identity(a.application_url), ats_identity(b.application_url)
    return bool(ia and ib and ia[0] == ib[0] and ia[2] != ib[2])
```

### 9.5 Fingerprint definition

```python
def fingerprint(job) -> str:
    return sha256("|".join([
        job.company_id,
        normalize_title(job.title),           # lowercase, strip punctuation, expand
                                              # SWE→software engineer, keep qualifiers
        canonical_location_set(job.locations),# sorted "us-ca-san-francisco" tokens
        job.employment_type or "unknown",
        job.internship_season or "",          # "summer-2027" — separates 2026 from 2027 reposts
    ]).encode()).hexdigest()
```

**"Software Engineer Intern" vs "Software Engineer Intern – AI Infrastructure":**
these are two separate requisitions with two different Greenhouse ids, so **L2 keeps them apart before
L3/L4 ever runs**, and `_is_distinct_ats_posting` blocks any later attempt to merge them.
`normalize_title` deliberately **keeps** the qualifier (`- ai infrastructure`), so their fingerprints
differ too. Correctly separated at two independent levels.

### 9.6 Should you use embeddings? **No.**

Semantic similarity solves "these two texts mean the same thing." Your actual problem is "these two
records point at the same requisition" — and you have the requisition ID in the URL. Embeddings would
add a vector store, an embedding bill, a similarity threshold to tune, and a new class of failure
(**silently merging two genuinely different internships and never alerting you about one of them**).
The downside is asymmetric: a missed alert is invisible, a duplicate alert is merely annoying.
**Prefer duplicates over false merges. Skip embeddings in V1 and V2.**

### 9.7 Hard cases

| Case | Handling |
|---|---|
| Same title, different locations | Location is *in* the fingerprint → separate canonical jobs. Correct: they're separate applications. |
| One job, multiple locations | ATS gives one id + `secondaryLocations[]` → **one** canonical job with `locations[]`. L2 guarantees this. |
| Reposted with a new job ID | New id → new canonical job → **alert** (it genuinely is newly applyable). Link via `related_job_id` for context. |
| Description edited | Same id → L0/L1 hit → `job_events` UPDATE row; alert only if a *material* field changed (§10). |
| Application URL changed | L2 ATS identity still matches → same canonical job, add a new `job_sources` row. |
| Syndicated / multi-board | L1 normalized URL collapses them. |
| Two sources, one canonical | `job_sources` gains a row; **no second alert** (§12). |

---

## 10. Job Lifecycle: New vs Updated vs Closed

### 10.1 State machine

```
                    ┌─────────┐
   first seen ─────►│   NEW   │──── alert sent ───►┌──────────┐
                    └─────────┘                    │  ACTIVE  │
                                                   └────┬─────┘
                          material field change ────────┤
                                                        ▼
                                                  ┌───────────┐
                                                  │  UPDATED  │──► back to ACTIVE
                                                  └───────────┘
        absent from N consecutive SUCCESSFUL runs ─────┤
                                                        ▼
                                                  ┌───────────┐
                            reappears ◄───────────│  CLOSED   │
                                │                 └───────────┘
                                ▼
                          ┌────────────┐
                          │  REOPENED  │──► ACTIVE
                          └────────────┘
```

### 10.2 Recommended alert policy

| Transition | Alert? | Reasoning |
|---|---|---|
| → **NEW** | ✅ **Always** | The core product. |
| → **UPDATED** (material) | 🟡 **Digest only, not push** | Matches your instinct but softer: batch into the daily digest. A title/location/deadline change is worth knowing, not worth a ping. |
| → **UPDATED** (cosmetic) | ❌ No | Description whitespace, metadata churn. Filter via `description_hash`. |
| → **CLOSED** | ❌ No | Agreed — nothing to act on. Record it. |
| → **REOPENED** | ✅ **Yes** | Agreed — it's newly applyable. Flag it as REOPENED so you recognise it. |
| Duplicate source | ❌ No | Attach source, update the existing record. |
| Unchanged | ❌ No | — |

"Material" = any of `title`, `locations`, `application_url`, `application_deadline`,
`employment_type`, `compensation`, or `description_hash` changing.

### 10.3 Closed-detection — the dangerous part

**Do not implement "absent ⇒ closed" naively.** I verified that Snyk, Deel, Bolt and HubSpot all return
**HTTP 200 with an empty job array**. A naive sweep would mark every job at those companies closed, then
mark them all *reopened* the next time data returned — a self-inflicted alert storm.

```python
def sweep_closed(source_id, seen_ids, run):
    if run.status != "success":            return    # never sweep on a failed run
    if run.jobs_fetched == 0:              return    # empty 200 is NOT "everything closed"
    prev = db.last_successful_run(source_id)
    if prev and run.jobs_fetched < prev.jobs_fetched * 0.5:
        run.flag("SUSPICIOUS_DROP"); alert_ops(source_id); return   # >50% drop → human check

    for job in db.active_jobs(source_id):
        if job.source_job_id in seen_ids:
            job.missing_run_count = 0; job.last_seen_at = now()
        else:
            job.missing_run_count += 1
            if job.missing_run_count >= 2:            # 2 consecutive misses
                job.status = "closed"; emit_event(job, "CLOSED")
```

Three guards — run succeeded, non-empty result, no cliff-drop — plus a 2-run confirmation. For the
Simplify feed you don't need any of this: the `active` boolean is authoritative.

---

## 11. Relevance Filtering — measured, not guessed

### 11.1 Empirical result

I pulled **7,260 real job titles** from 15 companies across Greenhouse and Ashby (Anthropic, Stripe,
Databricks, Waymo, Datadog, Roblox, Pinterest, Jane Street, Optiver, SpaceX, OpenAI, Snowflake, Cohere,
Ramp, Notion) and ran a candidate rule set:

| Bucket | Count | % | Action |
|---|---|---|---|
| Rejected — not early-career | 7,142 | **98.4%** | Deterministic, zero cost |
| Matched — early-career + technical | 76 | 1.05% | Auto-accept |
| **Ambiguous** | 38 | **0.52%** | → LLM |
| Rejected — early-career but non-technical | 4 | 0.06% | Deterministic |

**Conclusion: deterministic rules resolve 99.5% of titles. The LLM is needed for ~0.5%** — roughly
**2–5 calls per day** in steady state. At Haiku pricing that is a rounding error (well under $0.10/month).
This directly answers your "don't call an LLM for every job" requirement with a measured number.

### 11.2 False positives the real data exposed

These are the traps you'd have shipped without testing against live titles:

| Title | Trap |
|---|---|
| `Sensor **Placement** and Analysis Engineer` (Waymo) | "placement" is the UK word for internship — matched a senior IC role |
| `**Campus** Recruiter` (Jane Street) | "campus" appears in recruiting-team job titles |
| `Bastrop **Campus** Planning Manager` (SpaceX) | same trap, facilities role |
| `Head of Early Career Recruiting` (Notion) | "early career" describes the *team*, not the role |
| `[2026] **Senior** Machine Learning Engineer … PhD Early Career` (Roblox) | **Inverse trap** — genuinely early-career *despite* "Senior". A naive seniority blocklist would reject a role you want. |

**Design consequences:** (a) require `\bplacement\b` to co-occur with a season/year token;
(b) hard-reject `recruit|recruiting|recruiter|talent acquisition` before the campus rule runs;
(c) never let a seniority keyword *alone* reject — route "senior + early-career signal" to the LLM.

### 11.3 The pipeline

```python
def classify(job) -> Decision:
    t = normalize_title(job.title)

    # ── Stage 0: hard rejects (cheapest, catches the trap cases)
    if RECRUITING_RE.search(t):                 return REJECT("recruiting role")
    if EXEC_RE.search(t):                       return REJECT("director/vp/head")

    # ── Stage 1: early-career gate — 98.4% exit here
    intern  = INTERN_RE.search(t)      # intern|internship|co-op|apprentice|summer analyst
    newgrad = NEWGRAD_RE.search(t)     # new grad|university grad|entry-level|rotational|campus
    if not (intern or newgrad):
        if not early_career_signal(job.description, job.employment_type):
            return REJECT("not early career")

    # ── Stage 2: technical domain
    if not TECH_RE.search(t) and not TECH_RE.search(job.department or ""):
        if NONTECH_RE.search(t):                return REJECT("non-technical")
        return AMBIGUOUS("no technical signal")

    # ── Stage 3: seniority — only ambiguous, never fatal
    if SENIOR_RE.search(t) and not intern:
        return AMBIGUOUS("seniority + early-career conflict")   # the Roblox case

    # ── Stage 4: user eligibility (config-driven, §14)
    if not matches_preferences(job, prefs):     return REJECT("preferences")

    return ACCEPT(reasons=build_reasons(job))   # → "Software Engineering Internship / Summer 2027"

# AMBIGUOUS → single Haiku call, title + department + first 400 chars of description,
#             strict JSON out: {relevant: bool, category: str, reason: str}
#             Cache by description_hash so a repost never re-bills.
```

### 11.4 Where the LLM genuinely adds value

✅ The 0.5% ambiguous bucket · ✅ extracting `internship_season` from messy description prose
("Summer 2027", "May–Aug 2027", "rising senior") · ✅ extracting graduation-year requirements.
❌ Not for: every title, dedup, or anything a regex already does at 99.5% accuracy.

---

## 12. Database Design

### 12.1 Recommendation: **SQLite for V1, PostgreSQL when you outgrow it**

| Option | Cost | Verdict |
|---|---|---|
| **SQLite (WAL mode)** | **$0** | ✅ **V1.** Whole dataset is ~15k jobs / <500 MB. Single writer is fine — you have one writer. Zero ops, `cp` = backup, works offline. |
| PostgreSQL (self-hosted, same VPS) | $0 extra | ✅ **V2.** Move when you want concurrent workers, JSONB indexing, or a web UI. |
| Supabase | $0–25 | 🟡 Good free tier, but free projects **pause after inactivity** and you'd add network latency to every query for a single-user workload. |
| Firebase / DynamoDB | $0–ish | ❌ Document/KV models fight the relational joins at the heart of `canonical_job → job_sources`. |
| Managed Postgres (RDS/Neon) | $15–50 | ❌ Overkill for one user. |

Use **SQLAlchemy** so the SQLite→Postgres migration is a connection-string change. Avoid SQLite-only
syntax; keep `JSON` columns portable to JSONB.

### 12.2 Schema

```sql
CREATE TABLE companies (
    id              TEXT PRIMARY KEY,          -- 'anthropic'
    name            TEXT NOT NULL,
    tier            TEXT NOT NULL CHECK (tier IN ('big_tech','tier1','tier2','tier3')),
    careers_url     TEXT,
    status          TEXT DEFAULT 'active',     -- active | acquired | dropped
    successor_id    TEXT REFERENCES companies(id),   -- Loom→Atlassian, Neon→Databricks
    created_at      TIMESTAMP NOT NULL
);
CREATE TABLE company_aliases (               -- maps GitHub-feed names → company_id
    alias      TEXT PRIMARY KEY,             -- 'Facebook', 'Meta Platforms'
    company_id TEXT NOT NULL REFERENCES companies(id)
);

CREATE TABLE sources (
    id            TEXT PRIMARY KEY,           -- 'greenhouse:anthropic'
    kind          TEXT NOT NULL,              -- greenhouse|ashby|lever|workday|github_simplify|...
    company_id    TEXT REFERENCES companies(id),   -- NULL for multi-company feeds
    config        JSON NOT NULL,              -- {slug, tenant, site, ...}
    enabled       BOOLEAN DEFAULT 1,
    poll_interval_s INTEGER NOT NULL,
    priority      INTEGER DEFAULT 100,
    etag          TEXT,                       -- conditional GET cache
    last_modified TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    circuit_open_until   TIMESTAMP,
    health        TEXT DEFAULT 'healthy'      -- healthy|degraded|broken
);

CREATE TABLE canonical_jobs (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL REFERENCES companies(id),
    title               TEXT NOT NULL,
    normalized_title    TEXT NOT NULL,
    fingerprint         TEXT NOT NULL,
    ats_kind            TEXT,                 -- from URL: greenhouse|ashby|...
    ats_org             TEXT,
    ats_job_id          TEXT,
    canonical_url       TEXT NOT NULL,        -- normalized application URL
    locations           JSON NOT NULL,
    remote_type         TEXT,
    employment_type     TEXT,
    internship_season   TEXT,                 -- 'summer-2027'
    experience_level    TEXT,
    department          TEXT,
    compensation        JSON,
    application_deadline DATE,
    description_hash    TEXT,
    relevance_score     REAL,
    match_reasons       JSON,
    is_relevant         BOOLEAN NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'active',  -- active|closed|reopened
    posted_at           TIMESTAMP,
    first_seen_at       TIMESTAMP NOT NULL,
    last_seen_at        TIMESTAMP NOT NULL,
    missing_run_count   INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX ux_cj_canonical_url ON canonical_jobs(canonical_url);
CREATE UNIQUE INDEX ux_cj_ats          ON canonical_jobs(ats_kind, ats_org, ats_job_id)
                                        WHERE ats_job_id IS NOT NULL;
CREATE INDEX ix_cj_fingerprint ON canonical_jobs(fingerprint);
CREATE INDEX ix_cj_company_status ON canonical_jobs(company_id, status);
CREATE INDEX ix_cj_relevant_new  ON canonical_jobs(is_relevant, first_seen_at DESC);

-- ★ one canonical job ──< many source listings
CREATE TABLE job_sources (
    id                INTEGER PRIMARY KEY,
    canonical_job_id  INTEGER NOT NULL REFERENCES canonical_jobs(id) ON DELETE CASCADE,
    source_id         TEXT NOT NULL REFERENCES sources(id),
    source_job_id     TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    application_url   TEXT,
    content_hash      TEXT NOT NULL,
    raw_payload_id    INTEGER REFERENCES raw_payloads(id),
    scraper_version   TEXT NOT NULL,
    first_seen_at     TIMESTAMP NOT NULL,
    last_seen_at      TIMESTAMP NOT NULL,
    is_active         BOOLEAN DEFAULT 1
);
CREATE UNIQUE INDEX ux_js_source ON job_sources(source_id, source_job_id);   -- ← L0 dedup
CREATE INDEX ix_js_canonical ON job_sources(canonical_job_id);

CREATE TABLE job_events (
    id               INTEGER PRIMARY KEY,
    canonical_job_id INTEGER NOT NULL REFERENCES canonical_jobs(id),
    event_type       TEXT NOT NULL,   -- discovered|updated|closed|reopened|source_added
    changed_fields   JSON,
    before           JSON,
    after            JSON,
    source_id        TEXT,
    run_id           INTEGER REFERENCES scraper_runs(id),
    created_at       TIMESTAMP NOT NULL
);
CREATE INDEX ix_ev_job_time ON job_events(canonical_job_id, created_at DESC);

CREATE TABLE alerts (
    id                INTEGER PRIMARY KEY,
    canonical_job_id  INTEGER NOT NULL REFERENCES canonical_jobs(id),
    alert_type        TEXT NOT NULL,   -- new|reopened|digest
    channel           TEXT NOT NULL,   -- email|telegram
    idempotency_key   TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending|sent|failed|suppressed
    attempts          INTEGER DEFAULT 0,
    payload           JSON,
    created_at        TIMESTAMP NOT NULL,
    sent_at           TIMESTAMP
);
CREATE UNIQUE INDEX ux_alert_idem ON alerts(idempotency_key);          -- ★ the guarantee
CREATE INDEX ix_alert_pending ON alerts(status, created_at) WHERE status='pending';

CREATE TABLE scraper_runs (
    id              INTEGER PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    status          TEXT NOT NULL,   -- success|failed|not_modified|skipped_circuit_open
    http_status     INTEGER,
    not_modified    BOOLEAN DEFAULT 0,
    jobs_fetched    INTEGER DEFAULT 0,
    jobs_new        INTEGER DEFAULT 0,
    jobs_updated    INTEGER DEFAULT 0,
    jobs_duplicate  INTEGER DEFAULT 0,
    jobs_relevant   INTEGER DEFAULT 0,
    alerts_created  INTEGER DEFAULT 0,
    duration_ms     INTEGER,
    bytes_downloaded INTEGER,
    error_type      TEXT,
    error_message   TEXT,
    scraper_version TEXT
);
CREATE INDEX ix_runs_source_time ON scraper_runs(source_id, started_at DESC);

CREATE TABLE raw_payloads (
    id          INTEGER PRIMARY KEY,
    source_id   TEXT NOT NULL,
    run_id      INTEGER REFERENCES scraper_runs(id),
    sha256      TEXT NOT NULL,
    body_gzip   BLOB NOT NULL,
    fetched_at  TIMESTAMP NOT NULL
);
CREATE UNIQUE INDEX ux_raw_sha ON raw_payloads(source_id, sha256);   -- dedupe identical snapshots

CREATE TABLE user_preferences (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    config      JSON NOT NULL,     -- §14 preference document
    enabled     BOOLEAN DEFAULT 1
);
```

### 12.3 Relationships

```
companies 1 ──< sources 1 ──< scraper_runs
    │                │
    │                └──< raw_payloads
    │
    └──< canonical_jobs 1 ──< job_sources >── 1 sources     ★ the many-to-one core
              │
              ├──< job_events
              └──< alerts   (UNIQUE idempotency_key)
```

**Why `raw_payloads` dedupes by sha256:** most polls return byte-identical content. Storing one row per
distinct snapshot keeps the table small while preserving full replay history.

---

## 13. Alerting Architecture & Idempotency

### 13.1 The guarantee: a database constraint, not application logic

```python
def make_idempotency_key(job, alert_type, channel) -> str:
    # Deliberately excludes run_id and timestamp → the same logical event always
    # produces the same key, no matter how many times the scraper runs.
    return sha256(f"{job.id}:{alert_type}:{channel}:v1".encode()).hexdigest()
```

```python
def process(job: NormalizedJob, run: ScraperRun) -> None:
    with db.transaction():                          # ← one atomic unit
        canonical, is_new = resolve_canonical(job)
        upsert_job_source(canonical, job)           # ON CONFLICT (source_id, source_job_id) DO UPDATE

        if not is_new:
            if material_change(canonical, job):
                record_event(canonical, "updated")
                queue_digest(canonical)             # digest, not push
            return                                  # ★ no second alert, ever

        record_event(canonical, "discovered")
        if not canonical.is_relevant:
            return

        for channel in prefs.channels:
            db.execute(
              "INSERT INTO alerts (canonical_job_id, alert_type, channel, idempotency_key,"
              " status, payload, created_at) VALUES (?,?,?,?, 'pending', ?, ?)"
              " ON CONFLICT (idempotency_key) DO NOTHING",     # ★ the entire guarantee
              (canonical.id, "new", channel, make_idempotency_key(canonical,"new",channel),
               render(canonical), now()))
    # commit — the alert row and the job row land together or not at all
```

A **separate sender** drains the outbox:

```python
def drain_outbox():
    for alert in db.claim_pending(limit=20):        # UPDATE ... SET status='sending' WHERE status='pending'
        try:
            send(alert.channel, alert.payload)
            db.mark_sent(alert.id)
        except TransientError:
            db.bump_attempts(alert.id)              # retry w/ backoff; 5 strikes → 'failed' + ops alert
```

**Why this is genuinely idempotent:** running the scraper twice re-derives the *same*
`canonical_job_id` (L0 hits on `ux_js_source`), therefore the *same* `idempotency_key`, therefore the
second `INSERT` is a no-op at the database level. It holds even if the process crashes mid-run,
because the job row and alert row commit in one transaction. **Two runs cannot produce two emails.**

### 13.2 Channel recommendation

| Channel | V1? | Cost | Notes |
|---|---|---|---|
| **Email (Resend)** | ✅ | Free 3,000/mo (100/day) | Best archive + clickable links. |
| **Telegram bot** | ✅ | **Free, unlimited** | Trivial API, instant push to phone, no deliverability risk. Strongest push option. |
| Discord webhook | V2 | Free | Nice embeds; add if you want a searchable channel. |
| Slack | ❌ | — | No advantage over Telegram here. |
| SMS (Twilio) | ❌ | ~$0.008/msg | Costs money, 160 chars, no links worth clicking. |
| Push (ntfy.sh) | Optional | Free | Good self-hosted alternative to Telegram. |

**Recommended V1: Telegram for instant push + email for the daily digest and archive.**

### 13.3 Alert format

```
🚨 New Internship

Company:   Anthropic  (Tier 1)
Role:      Software Engineer Intern, Model Infrastructure
Location:  San Francisco, CA  ·  On-site
Type:      Internship · Summer 2027
Posted:    August 20, 2026

Why it matched:
  ✓ Software Engineering Internship
  ✓ Summer 2027 term
  ✓ US location (CA)
  ✓ Tier 1 company

Sources (1 canonical job):
  • Company Career Page (Greenhouse)   discovered 18:32
  • Simplify GitHub feed               discovered 18:47   ← no second alert

Apply (official):
  https://job-boards.greenhouse.io/anthropic/jobs/5391376008

First discovered: 2026-08-20 18:32 UTC
```

**Rule: `Apply` always links to the ATS/company URL, never an aggregator.** Rank sources by
`ats > company_site > github_feed` and use the highest-ranked `application_url`.

---

## 14. Configuration System

Companies and preferences are **data, not code**. `companies.yaml` is generated from the verified
inventory in §3 (I've already produced `research/source_inventory.json` with all 114 rows).

```yaml
# companies/companies.yaml
defaults:
  enabled: true
  locations: ["United States"]
  filters: { internships: true, new_grad: true }

companies:
  - id: anthropic
    name: Anthropic
    tier: tier1
    careers_url: https://www.anthropic.com/careers
    connectors:
      - kind: greenhouse
        slug: anthropic
        verified_at: 2026-08-20
        verified_job_count: 494
    poll_interval: 15m            # tier1 → fast

  - id: openai
    name: OpenAI
    tier: tier1
    connectors:
      - kind: ashby
        slug: openai
        options: { include_compensation: true }
        verified_at: 2026-08-20
        verified_job_count: 741
    poll_interval: 15m

  - id: nvidia
    name: NVIDIA
    tier: big_tech
    connectors:
      - kind: workday
        tenant: nvidia
        wd_host: wd5
        site: NVIDIAExternalCareerSite
        verified_at: 2026-08-20
    poll_interval: 30m

  - id: apple
    name: Apple
    tier: big_tech
    connectors: []                       # ← no legitimate direct route
    coverage: github_feed_only
    note: "jobs.apple.com/api returns HTTP 401. Verified 2026-08-20."
    aliases: ["Apple Inc.", "Apple Inc"]

  - id: neon
    name: Neon
    tier: tier3
    enabled: false
    status: acquired
    successor: databricks
    note: "neon.com/careers 301s to databricks.com. Verified 2026-08-20."
```

```yaml
# config/preferences.yaml   — never hard-code these
profile:
  graduation_year: [2027]
  degree: [Bachelors, Masters]
  majors: [Computer Science, Computer Engineering, Data Science]

eligibility:
  work_authorization: us_citizen        # drives the `sponsorship` filter
  requires_sponsorship: false

seasons:   [Summer 2027, Fall 2027, Spring 2027]
role_types: [internship, new_grad]

locations:
  countries: [US]
  states:    []                          # empty = any
  cities:    []
  remote:    { include: true, only: false }
  international: false

categories: [software, ai_ml, data, infrastructure, security, quant]
skills_boost: [python, go, rust, distributed systems, pytorch]

compensation:
  min_hourly: null                       # null = don't filter

alerts:
  channels: [telegram, email]
  quiet_hours: { start: "23:00", end: "07:00", tz: America/Los_Angeles }
  digest: { enabled: true, at: "08:30" }
  max_per_hour: 10                       # burst guard
```

---

## 15. Scheduling

### 15.1 Verified facts that drive the schedule

- **Greenhouse and `raw.githubusercontent.com` both honour `If-None-Match` → HTTP 304, 0 bytes.**
  Unchanged polls are nearly free, so frequency is cheap where ETags work.
- **Simplify's `listings.json` commits every ~30 minutes.** Polling faster gains nothing.
- **speedyapply runs `cron: '0 12 * * *'` — once daily.** Polling hourly is 24× waste.
- **GitHub REST unauthenticated = 60 req/hr** (I hit this limit). Authenticated = 5,000/hr.
- **Lever's robots.txt requests `Crawl-delay: 1`.** Honour it.

### 15.2 Recommended intervals

| Source group | In-season (Aug–Nov) | Off-season | Rationale |
|---|---|---|---|
| Tier 1 + Big Tech ATS (ETag) | **15 min** | 60 min | 304s cost ~nothing; these matter most |
| Tier 2 ATS | **30 min** | 2 h | |
| Tier 3 ATS | **2 h** | 6 h | Lower urgency, higher count |
| Workday / Eightfold (POST, **no ETag**) | **60 min** | 3 h | Real payload every time — be frugal |
| **Simplify `listings.json`** | **20 min** | 60 min | Source refreshes every 30 min; 20 min avoids phase-lock |
| **speedyapply (×2 repos)** | **1×/day at 12:15 UTC** | 1×/day | Source is daily; anything more is waste |
| Amazon / Intuit custom | 60 min | 3 h | Be conservative on non-ATS endpoints |

**Season awareness:** Summer-2027 internship postings cluster **August–November 2026** — i.e. right
now. Make the multiplier a config value (`season_profile: peak | normal | quiet`) rather than a code branch.

**Politeness rules:** stagger start times with jitter (never fire 100 requests at `:00`), cap
global concurrency at 8, cap per-host concurrency at 2, and send a real
`User-Agent` identifying the project with a contact address. My probes used exactly this and were
never rate-limited.

**Daily request volume (in-season estimate):** ~100 ATS sources × 96 polls/day ≈ 9,600 requests,
the large majority returning 304 with an empty body. That's a trivial load for both sides.

**Webhooks?** Not available anywhere here — no ATS offers public job-board webhooks, and you can't add
webhooks to repos you don't own. **The system is poll-based by necessity, which is fine given ETags.**

---

## 16. Infrastructure & Deployment

| | **A: One VPS** ✅ | B: Serverless | C: Managed queue |
|---|---|---|---|
| Stack | Docker + SQLite + APScheduler | GH Actions + Supabase + Workers | Cloud Run + Cloud Tasks + Postgres |
| Cost/mo | **$4–6** | $0–10 | $15–40 |
| Reliability | High — one process, one box | Medium — cold starts, 6h job caps, state in a remote DB | High |
| Maintenance | **Low** — `docker compose pull && up -d` | Medium — YAML sprawl, painful local repro | Medium-high |
| Debugging | **Easy** — `docker logs`, `sqlite3` on the spot | **Hard** — no shell, no local DB, log hunting | Medium |
| Scalability | Vertical only (irrelevant here) | High | High |

### Recommendation: **Option A — a single small VPS.**

Hetzner CX22 (~€3.79/mo) or a $6 DigitalOcean droplet. You explicitly value reliability and low
maintenance over scalability, and a single always-on process with a local database is the most
debuggable system that exists. Serverless would trade a $5 bill for state-management complexity and
the inability to open a shell when something breaks at 2am.

```yaml
# docker-compose.yml (V1)
services:
  monitor:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/data              # SQLite + raw payloads
      - ./logs:/logs
    healthcheck:
      test: ["CMD", "python", "-m", "src.healthcheck"]
      interval: 5m
```

**Backups:** nightly `sqlite3 .backup` → `restic`/`rclone` to Backblaze B2 (~$0.06/mo at this size).
**If you truly want $0:** GitHub Actions on a schedule with SQLite committed to a private repo works,
but state-in-git is fragile and Actions' shortest reliable cron is ~5–15 min with no guarantees.
Worth $5 to avoid.

---

## 17. Technology Recommendation

| Layer | Choice | Why |
|---|---|---|
| **Language** | **Python 3.12** | The ecosystem fit is decisive: Pydantic for schema validation, `rapidfuzz` for L4 matching, `dateparser` for messy dates, plus the Anthropic SDK. TypeScript is the only real alternative and wins nothing here. |
| HTTP | **httpx** (async) | HTTP/2, connection pooling, native async, clean timeout semantics. Better than `requests` for 100 concurrent sources. |
| Parsing | **selectolax** (+ BeautifulSoup fallback) | Only needed for speedyapply tables and Intuit. Fast. |
| Validation | **Pydantic v2** | Connector output contracts. A schema violation = a caught scraper break, not silent bad data. |
| DB / ORM | **SQLite + SQLAlchemy 2.0** | Portable to Postgres by connection string. |
| Migrations | **Alembic** | |
| Scheduler | **APScheduler** (in-process) | No Redis, no Celery, no broker to babysit. Celery is the right answer at 10k sources; you have ~100. |
| Retries | **tenacity** | Exponential backoff + jitter. |
| Fuzzy match | **rapidfuzz** | `token_set_ratio` for L4. |
| Logging | **structlog** → JSON | Greppable, ships to anything later. |
| Errors | **Sentry** (free tier) | Stack traces with context. |
| Uptime | **Healthchecks.io** (free) | Dead-man's switch — pings *you* when the box dies. |
| Email | **Resend** (free 3k/mo) | |
| Push | **Telegram Bot API** | Free, instant. |
| LLM | **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) | Only for the 0.5% ambiguous bucket. |
| Tests | **pytest** + **respx** | Record real API responses as fixtures; connectors testable offline. |
| Lint | **ruff** + **mypy** | |

**Explicitly rejected:** Scrapy (built for crawling link graphs; you're calling ~10 JSON APIs),
Playwright/Selenium (§6.4 — no legitimate need), Celery/Redis (broker overhead for 100 tasks),
Crawlee (same as Scrapy), any vector DB (§9.6).

**Fetch strategy hierarchy, as you specified:**
`Official API (86%) > JSON endpoint > RSS/feed > static HTML (speedyapply) > browser rendering (never)`.

---

## 18. Resilience

### 18.1 Per-source policy

```python
FETCH_POLICY = dict(
    connect_timeout=10, read_timeout=30, total_timeout=60,
    retries=3, backoff="exponential", base=2, jitter=True,   # 2s, 4s, 8s ±25%
    retry_on=[429, 500, 502, 503, 504, ConnectError, ReadTimeout],
    never_retry_on=[400, 401, 403, 404],                     # retrying these is abuse
    respect_retry_after=True,
    conditional_get=True,
)
```

### 18.2 Circuit breaker

```
consecutive_failures >= 3  → health='degraded', interval ×4,  notify (low priority)
consecutive_failures >= 6  → health='broken',   circuit OPEN 6h, notify (high priority)
circuit open               → skip, log 'skipped_circuit_open'
one success                → reset to healthy, restore interval
```

This matters because a broken source must not consume the request budget of 99 healthy ones.

### 18.3 Schema validation as break detection

Every connector returns `list[NormalizedJob]` through Pydantic. If Greenhouse renames a field, the
model raises, the run is marked `failed` with `error_type='schema'`, the raw payload is preserved, and
you get an alert naming the field. **This is how you learn a scraper broke — before the silence gets long.**

### 18.4 Sanity guards (learned from live probing)

| Guard | Trigger | Action |
|---|---|---|
| Empty-success | HTTP 200 + `jobs: []` (real: Snyk, Deel, Bolt, HubSpot) | Do **not** sweep closures; count as `degraded` if it persists |
| Cliff drop | `jobs_fetched < 50%` of last successful run | Flag `SUSPICIOUS_DROP`, skip sweep, notify |
| Payload explosion | Response > 30 MB (real: SpaceX `content=true` = 24 MB) | Abort, log, never buffer unbounded |
| Zero-relevant streak | 0 relevant jobs from a formerly productive source for 14 days | Health warning — filters or parser may have silently broken |
| Slug drift | Career page no longer references the configured slug | Monthly job; open a config-review task |

---

## 19. Observability

### 19.1 Per-run metrics (all already columns on `scraper_runs`)

`status` · `http_status` · `not_modified` · `jobs_fetched` · `jobs_new` · `jobs_updated` ·
`jobs_duplicate` · `jobs_relevant` · `alerts_created` · `duration_ms` · `bytes_downloaded` ·
`error_type` · `error_message` · `scraper_version`

### 19.2 Health rollup

```sql
-- The one query that answers "is anything silently broken?"
SELECT s.id, s.health,
       MAX(r.started_at)                                     AS last_attempt,
       MAX(CASE WHEN r.status='success' THEN r.started_at END) AS last_success,
       s.consecutive_failures
FROM sources s LEFT JOIN scraper_runs r ON r.source_id = s.id
WHERE s.enabled GROUP BY s.id
HAVING last_success IS NULL
    OR last_success < datetime('now', '-6 hours')
ORDER BY last_success NULLS FIRST;
```

### 19.3 Alerting on the system itself

| Signal | Threshold | Channel |
|---|---|---|
| Source no successful run | > 6× its interval | Telegram (low) |
| Source circuit opened | immediate | Telegram (high) |
| Schema validation failure | immediate | Telegram (high) + Sentry |
| **Whole system silent** | no heartbeat in 30 min | **Healthchecks.io → email/SMS** |
| Alert outbox stuck | pending > 30 min | Telegram (high) |
| Cliff drop / suspicious | immediate | Telegram (medium) |

**The dead-man's switch is the important one.** Every internal monitor fails silently if the process
dies. Healthchecks.io (free) pings *you* when the ping *stops* — the only monitor that survives total failure.

### 19.4 Daily digest email (08:30)

```
Sources: 103 healthy · 2 degraded · 1 broken
Polls: 9,412  (8,981 not-modified · 431 fetched)
Jobs: 47 new · 12 updated · 89 duplicates collapsed
Relevant: 6 new  →  6 alerts sent  ·  0 failed
LLM calls: 3   ($0.002)
⚠ BROKEN: ashby:snyk — 7 consecutive empty responses
⚠ DEGRADED: workday:salesforce — 2 timeouts
```

**Tooling:** structlog JSON → files + `docker logs`; Sentry free tier for exceptions;
Healthchecks.io free for the dead-man's switch. **Total cost: $0.** Skip Grafana/Prometheus in V1 — a
SQL query and a daily email give you everything at this scale.

---

## 20. Cost Analysis

### Tier 1 — MVP (~100 companies, ATS + GitHub, email+Telegram)

| Item | Monthly |
|---|---|
| Hetzner CX22 VPS | **$4.10** |
| SQLite | $0 |
| Resend (free 3k/mo) | $0 |
| Telegram | $0 |
| Sentry (free) | $0 |
| Healthchecks.io (free) | $0 |
| Backblaze B2 backups | ~$0.06 |
| Domain (optional) | ~$1 |
| **Total** | **≈ $4–6 / month** ✅ |

Your **$0–20/month target is comfortably realistic** — the MVP lands near the bottom of it.

### Tier 2 — Medium (adds LLM classification, more sources, Postgres)

| Item | Monthly |
|---|---|
| VPS (upgrade to 4 GB) | $7.50 |
| Postgres (same box) | $0 |
| **LLM (Haiku, ~0.5% of titles)** | **< $0.50** |
| Resend paid (if > 3k emails) | $0–20 |
| **Total** | **≈ $8–28 / month** |

The LLM line is the surprise: because rules resolve 99.5% of titles (§11.1), classification costs
**cents**, not dollars. Measured, not assumed.

### Tier 3 — Advanced (embeddings, browser automation, paid data)

| Item | Monthly | Verdict |
|---|---|---|
| Embeddings + vector store | $10–30 | ❌ Not recommended (§9.6) |
| Browser automation (Playwright + proxies) | $50–300 | ❌ Not recommended (§6.4) |
| Residential proxies | $75–500 | ❌ **Never** (§21) |
| SerpApi Google Jobs | **$25–275** (1k–30k searches; 100 free/mo) | 🟡 Only if you want non-target companies |
| Adzuna API | **$0** (~1,000 calls/mo free) | 🟡 Cheapest legitimate aggregator to experiment with |
| JSearch (RapidAPI) | ~$10–100 | 🟡 Wrapper with marketplace markup |
| Coresignal / Bright Data / licensed feeds | $500–2,000+ | ❌ Wildly disproportionate |

**Guidance: none of Tier 3 is necessary.** The expensive options buy coverage of companies you didn't
ask for, at 10–100× the total cost of the system that covers the ones you did.

---

## 21. Legal / ToS Risk Matrix

| Source | Class | robots.txt evidence (verified 2026-08-20) | Verdict |
|---|---|---|---|
| Greenhouse Job Board API | 🟢 **Official API** | `boards-api.greenhouse.io/robots.txt`: only `Disallow: /embed/` | **Use.** Documented public API, no auth. |
| Ashby Posting API | 🟢 **Official API** | Documented public endpoint; `api.ashbyhq.com` is an API host | **Use.** |
| Lever Postings API | 🟢 **Official API** | `api.lever.co/robots.txt`: `Allow: /`, `Crawl-delay: 1` | **Use**, honour crawl-delay. |
| Workday CXS | 🟡 **Public structured data** | `nvidia.wd5...`: `Allow: /NVIDIAExternalCareerSite/` | **Use**, modestly. Undocumented but publicly served and robots-permitted. |
| Eightfold `apply/v2/jobs` | 🟡 **Public structured data** | Publicly served, no auth | **Use**, modestly. |
| Rippling ATS board API | 🟡 **Public structured data** | Publicly served, no auth | **Use.** |
| **SmartRecruiters API** | 🟡 **Caution — conflicting signals** | `api.smartrecruiters.com/robots.txt`: `User-agent: LinkedInBot → Allow: /v1/companies/`; **`User-agent: * → Disallow: /`** | Documented public API, but robots disallows non-LinkedIn crawlers. **Avoid unless needed**; none of your primary companies require it. |
| Amazon `search.json` | 🟢 **Public structured data** | `amazon.jobs/robots.txt`: only `/internal` disallowed | **Use**, low rate. |
| GitHub REST + raw | 🟢 **Official API** | Documented; use a PAT | **Use.** |
| Company career pages (Schema.org) | 🟢 | Per-site check required | **Use** where robots permits. |
| **Simplify (site)** | 🟡 | — | **Don't** — use their GitHub repo instead. |
| **Jobright** | 🔴 | `Disallow: /api/`, `/api/*` | **Do not scrape.** |
| **Handshake** | 🔴 | Allowlist robots; job pages not listed; API is institution-only | **Do not scrape.** |
| **Indeed** | 🔴 | `Disallow: /graphql`, `/api/getrecjobs`; Publisher API dead since 2023 | **Do not scrape.** |
| **LinkedIn** | 🔴 | *"The use of robots or other automated means to access LinkedIn without the express permission of LinkedIn is strictly prohibited."* | **Do not scrape.** |
| **Tesla** | 🔴 | Akamai 403 on all requests including `robots.txt` | **Do not scrape.** Unambiguous refusal. |

### 21.1 The legal principle that matters here

*hiQ Labs v. LinkedIn* (9th Cir. 2022) held the **CFAA** does not prohibit scraping publicly available
data. But on remand the district court granted LinkedIn summary judgment on **breach of contract**, and
hiQ settled with a **$500,000 judgment** in December 2022. The lesson is precise:
**"not a computer crime" is not the same as "permitted."** A site's Terms of Service are an enforceable
contract, and robots.txt is the clearest published statement of intent. This system respects both.

### 21.2 Techniques this design will not use

❌ CAPTCHA solving · ❌ browser-fingerprint spoofing · ❌ stealth/undetected browser drivers ·
❌ authentication bypass · ❌ paywall circumvention · ❌ residential-proxy rotation to evade blocks ·
❌ abusing authenticated private APIs · ❌ ignoring `robots.txt`, `429`s or `Retry-After`.

**Instead:** documented public APIs, publicly served JSON endpoints that robots.txt permits,
official GitHub APIs, a truthful `User-Agent` with a contact address, conditional GETs to minimise
load, and conservative rate limits. If a source says no — as Tesla does with a 403 — the answer is to
stop, not to escalate.

### 21.3 One caveat on the GitHub repositories

All three repos have **no license file**, which under default copyright means "all rights reserved" for
the *compilation*. Individual facts (a company posted a job at a URL) are not copyrightable, and
personal, non-redistributive use of a public repo is a very low-risk activity. But **do not
re-publish these datasets** as your own feed or product. Personal alerts: fine. A public mirror: don't.

---

## 22. Existing Open-Source Projects

I searched GitHub's API by stars across job-scraper, ATS-scraper, aggregator and internship-tracker
queries. **Finding: there is no production-worthy open-source project that solves this problem.** The
space is a long tail of small personal repos plus one strong library aimed at the boards you should avoid.

| Project | URL | Stars | Last activity | License | Solves | Reusable? | Production-worthy? |
|---|---|---|---|---|---|---|---|
| **JobSpy** | `github.com/speedyapply/JobSpy` | **4,118** | 2026-02-18 | **MIT** | Scrapes LinkedIn/Indeed/Glassdoor/Google/ZipRecruiter | ⚠ **Reference only** — its target boards are exactly the 🔴 sources. Read its *normalization* and title-parsing code, don't run its scrapers. | Yes as a library, ✗ for this use case |
| **SimplifyJobs/Summer2027-Internships** | as given | **46,625** | 2026-08-21 | None ⚠ | The listings dataset itself | ✅ **Consume as data** (§5.1) — the highest-value asset found | ✅ as a data source |
| **speedyapply/2027-SWE-College-Jobs** | as given | 8,893 | 2026-08-20 | None ⚠ | Daily SWE intern/new-grad tables + salary | ✅ Consume as data | ✅ as a data source |
| **speedyapply/2027-AI-College-Jobs** | as given | 6,175 | 2026-08-20 | None ⚠ | Daily AI/ML tables | ✅ Consume as data | ✅ as a data source |
| Feashliaa/job-board-aggregator | `github.com/Feashliaa/job-board-aggregator` | 121 | 2026-08-20 | MIT | Multi-board aggregator, actively developed | 🟡 Skim for ATS endpoint lists | ✗ too small/young |
| adgramigna/job-board-scraper | `github.com/adgramigna/job-board-scraper` | 46 | 2025-11-27 | MIT | Greenhouse + Lever scraping w/ dbt | 🟡 Useful reference for GH/Lever field handling | ✗ |
| YvetteZheng0812/ats-job-scraper | — | 3 | 2026-06-02 | MIT | 7 ATS platforms | 🟡 Endpoint reference only | ✗ |
| rhowell7/job-scraper | — | 4 | 2025-10-08 | MIT | Greenhouse + Lever leads | ✗ | ✗ |

**Recommendation: build it yourself, reuse the *data*, not the *code*.** The one genuinely popular
library (JobSpy) targets the boards this design deliberately excludes, and no existing project does the
canonical-job/dedup/alert-idempotency work that is the actual hard part here. The three GitHub
repositories, though, are excellent — as sources.

---

## 23. Data Providers / APIs Evaluated

| Provider | Cost | Coverage | Legality | Freshness | Verdict |
|---|---|---|---|---|---|
| **Company ATS public APIs** | **$0** | 86% of your list | 🟢 Documented | Real-time | ✅ **Primary** |
| **GitHub feeds** | **$0** | Big Tech + 727 companies | 🟢 Public repos | 30 min / daily | ✅ **Primary** |
| Adzuna API | $0 (~1k calls/mo free) | Broad, shallow per-job | 🟢 Official | Hours-days | 🟡 Optional V2 experiment |
| JSearch (RapidAPI) | ~$10–100/mo | Aggregated | 🟡 Wrapper, ~30% markup | Hours | 🟡 Only if desperate |
| SerpApi Google Jobs | $25–275/mo (100 free) | Very broad | 🟢 Official | Hours | 🟡 Expensive for the gain |
| Indeed Publisher API | — | — | ❌ **Discontinued 2023** | — | ❌ Unavailable |
| LinkedIn Talent Solutions | Partner-only | — | ❌ Not open to individuals | — | ❌ Unavailable |
| Handshake EDU API | Institution-only | — | ❌ Career Services partners only | — | ❌ Unavailable |
| Coresignal / Bright Data | $500–2,000+/mo | Very broad | 🟡 Licensed | Daily | ❌ Disproportionate |

**Conclusion: no paid API is necessary.** The free sources cover 86% directly and the remainder
via GitHub. Paid providers add companies you didn't ask about at 10–100× the system's total cost.

---

## 24. MVP — exactly what V1 contains

### ✅ In V1

1. **Three ATS connectors: Greenhouse, Ashby, Lever** → **92 companies (80.7%)**.
2. **Simplify `listings.json` connector** → adds Apple, Google, Meta, Tesla, TikTok, ByteDance + 700 more.
3. **SQLite + SQLAlchemy** with the §12 schema (`canonical_jobs` ──< `job_sources`).
4. **Dedup levels L0–L3** (source id → normalized URL → ATS identity → fingerprint). *L4 fuzzy is V2.*
5. **Deterministic relevance rules** (§11.3 stages 0–2 + preferences). *LLM is V2.*
6. **Email alerts (Resend) + Telegram**, with outbox + `UNIQUE(idempotency_key)`.
7. **`companies.yaml` config** generated from `research/source_inventory.json`.
8. **`scraper_runs` logging + daily digest + Healthchecks.io dead-man's switch.**
9. **APScheduler** with tier-based intervals + ETag conditional GETs.
10. **Docker Compose** on one VPS, nightly SQLite backup.

### ⏭ Deferred to V2

| Deferred | Why |
|---|---|
| Workday, Eightfold, Rippling, Amazon, Intuit connectors | +6 companies for 5 more connectors — poor ratio until the core is stable |
| speedyapply markdown parsers | Simplify already covers most of it; speedyapply adds salary |
| LLM classification of the ambiguous 0.5% | Log ambiguous cases in V1; you'll have real data to tune against |
| L4 fuzzy dedup | L0–L3 should handle nearly everything; measure the residue first |
| Discord, web UI, Postgres, full-text search | Nice-to-have |
| **Embeddings, browser automation, LinkedIn/Indeed** | **Never** (§9.6, §6.4, §21) |

**Why this cut:** V1 is 4 connectors and covers ~100 of 114 companies. Every deferred item has a worse
coverage-per-unit-of-work ratio than shipping and running the core loop for a week.

---

## 25. Phased Implementation Plan

| Phase | Work | Effort | Exit criteria |
|---|---|---|---|
| **0. Research** | ✅ **Done** — 114 companies probed, `source_inventory.json` written, boards assessed, legal matrix built | ~~—~~ | This document |
| **1. Foundation** | Repo, `pyproject`, ruff/mypy/pytest, settings, structlog, SQLAlchemy models + Alembic, `NormalizedJob` Pydantic contract, `companies.yaml` loader | **1–2 days** | `pytest` green; DB migrates; config validates all 114 rows |
| **2. ATS connectors** | `BaseConnector` (httpx + ETag + retries + circuit breaker), then Greenhouse → Ashby → Lever. Fixtures recorded from live responses | **2–3 days** | 92 companies return validated `NormalizedJob`s offline in tests |
| **3. Company coverage** | Wire all 92 via config (**no new code**), verify counts vs §3 baselines, quarantine mismatches | **0.5 day** | Full run < 5 min, ≥ 95% sources healthy |
| **4. GitHub connector** | Simplify `listings.json` + ETag + company alias resolution + URL→company mapping | **1 day** | Apple/Google/Meta/Tesla/TikTok jobs land in DB |
| **5. Deduplication** | URL normalizer, ATS identity extractor, fingerprint, L0–L3 cascade, `_is_distinct_ats_posting` guard | **2 days** | Anthropic job from Greenhouse + Simplify = 1 canonical, 2 `job_sources` |
| **6. Relevance** | Rule stages, lexicons (incl. the §11.2 traps), preferences, `match_reasons` | **1–2 days** | Replays the 7,260-title corpus with ≥ 99% agreement; the 5 known traps all handled |
| **7. Alerts** | Outbox, idempotency key, renderer, Resend + Telegram, quiet hours | **1–2 days** | **Run the pipeline twice → exactly one email.** |
| **8. Lifecycle + monitoring** | Closed sweep w/ 3 guards, `job_events`, health rollup, daily digest, Healthchecks.io, Sentry | **1–2 days** | Kill a source → alert within 6× interval; empty-200 does not mass-close |
| **9. Production** | Dockerfile, compose, scheduler intervals + jitter, backups, README/runbook | **1 day** | 7 days unattended, zero duplicate alerts |
| **10. V2** | Workday/Eightfold/Rippling/Amazon/Intuit, speedyapply, LLM, L4 | 3–5 days | — |

**Total to a running V1: ~10–14 focused days** (≈ 2–3 calendar weeks part-time).

---

## 26. Repository Structure

```
job-alerts/
├── README.md
├── pyproject.toml                 # ruff · mypy · pytest config
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
│
├── config/
│   ├── companies.yaml             # ← generated from research/source_inventory.json
│   ├── preferences.yaml           # eligibility + alert prefs (§14)
│   └── schedules.yaml             # tier → interval, season profiles
│
├── src/
│   ├── main.py                    # entrypoint: scheduler | run-once | backfill
│   ├── healthcheck.py             # docker HEALTHCHECK target
│   ├── config/                    # pydantic-settings + YAML loaders + validation
│   ├── models/
│   │   ├── db.py                  # SQLAlchemy ORM
│   │   └── job.py                 # NormalizedJob, Location, Compensation
│   ├── database/                  # session, repositories, migrations/
│   ├── connectors/
│   │   ├── base.py                # BaseConnector: ETag, retry, circuit breaker, raw capture
│   │   ├── registry.py            # kind → class
│   │   ├── ats/
│   │   │   ├── greenhouse.py  ashby.py  lever.py
│   │   │   └── workday.py  eightfold.py  rippling.py        # V2
│   │   ├── github/
│   │   │   ├── simplify.py        # listings.json (dev branch)
│   │   │   └── speedyapply.py     # markdown tables            # V2
│   │   └── custom/
│   │       └── amazon.py  intuit.py                            # V2
│   ├── normalization/
│   │   ├── titles.py  locations.py  urls.py  seasons.py
│   ├── deduplication/
│   │   ├── identity.py            # ats_identity()
│   │   ├── fingerprint.py
│   │   └── resolver.py            # L0–L4 cascade
│   ├── relevance/
│   │   ├── rules.py  lexicons.py  preferences.py
│   │   └── llm.py                 # ambiguous-only, cached      # V2
│   ├── lifecycle/                 # state machine + guarded closed-sweep
│   ├── notifications/
│   │   ├── outbox.py  renderer.py  email.py  telegram.py
│   ├── scheduler/                 # APScheduler wiring, jitter, season profiles
│   ├── monitoring/                # run recorder, health rollup, digest, heartbeat
│   └── cli/                       # verify-sources, replay, stats, test-alert
│
├── research/                      # ← this phase's output, kept in-repo
│   ├── RESEARCH_REPORT.md
│   ├── source_inventory.json      # 114 verified rows
│   └── probes/                    # reproducible probe scripts
│
├── tests/
│   ├── fixtures/                  # recorded API responses (respx)
│   ├── test_connectors/  test_dedup/  test_relevance/  test_alerts/
│   └── test_idempotency.py        # ★ run twice → one alert
│
├── data/                          # sqlite + raw payloads (gitignored)
└── docs/
    ├── RUNBOOK.md                 # "a scraper broke — what now"
    └── ADDING_A_COMPANY.md
```

**Changes from your draft:** added `research/` (keep the evidence next to the code), `lifecycle/`
(job state machine is its own concern, not part of dedup), `cli/` (operational commands are how you'll
debug), `docs/RUNBOOK.md`, and `tests/fixtures/` (recorded responses are what make connectors testable
without hitting live APIs).

---

## 27. End-to-End Data Flow Example

```
[1] 2026-08-20 18:32:07  Anthropic publishes
    "Software Engineer Intern, Model Infrastructure" · San Francisco, CA

[2] 18:32:15  greenhouse:anthropic fires (tier1, 15 min)
    GET boards-api.greenhouse.io/v1/boards/anthropic/jobs
    If-None-Match: W/"2c0694…"          →  200 (changed), 355 KB
    raw_payloads ← gzip blob, sha256

[3] NORMALIZE  → NormalizedJob(
      source_id='greenhouse:anthropic', source_job_id='5391376008',
      title='Software Engineer Intern, Model Infrastructure',
      application_url='https://job-boards.greenhouse.io/anthropic/jobs/5391376008?gh_src=abc',
      locations=[SF, CA, US], posted_at=2026-08-20T18:32:07)

[4] RELEVANCE
      Stage 0 recruiting/exec? no
      Stage 1 INTERN_RE hit "Intern"                    ✓
      Stage 2 TECH_RE hit "Software Engineer"           ✓
      Stage 3 no seniority conflict                     ✓
      Stage 4 prefs: US ✓ · Summer 2027 ✓ · software ✓
      → ACCEPT ["Software Engineering Internship","Summer 2027","US location","Tier 1"]

[5] DEDUP
      L0 (greenhouse:anthropic, 5391376008)             → miss
      L1 normalize_url → …/anthropic/jobs/5391376008    → miss   (gh_src stripped)
      L2 ats_identity ('greenhouse','anthropic','5391376008') → miss
      L3 fingerprint                                    → miss
      ⇒ CREATE canonical_jobs #4471   (is_new = True)

[6] PERSIST (one transaction)
      canonical_jobs #4471
      job_sources   #9912 → (#4471, greenhouse:anthropic, 5391376008)
      job_events         → 'discovered'
      alerts  INSERT ON CONFLICT DO NOTHING
              idempotency_key = sha256("4471:new:telegram:v1")   → inserted
              idempotency_key = sha256("4471:new:email:v1")      → inserted
      COMMIT

[7] 18:32:19  outbox drains → Telegram + email sent.   ✅ ONE ALERT

──────────────────────────────────────────────────────────────────────
[8] 18:47:02  github:simplify fires (20 min)
      raw.githubusercontent.com/…/listings.json
      If-None-Match → 200 (changed), 10.8 MB
      Record: { company_name:"Anthropic",
                title:"Software Engineer Intern, Model Infrastructure",
                url:"https://job-boards.greenhouse.io/anthropic/jobs/5391376008",
                terms:["Summer 2027"], active:true }

[9] NORMALIZE → source_id='github:simplify', source_job_id='<simplify uuid>'
      company alias "Anthropic" → company_id 'anthropic'

[10] DEDUP
      L0 (github:simplify, <uuid>)                      → miss   (new source row)
      L1 normalize_url → …/anthropic/jobs/5391376008    → ★ HIT canonical #4471
      ⇒ is_new = False

[11] PERSIST
      job_sources #9948 → (#4471, github:simplify, <uuid>)
      job_events        → 'source_added'
      canonical_jobs #4471.last_seen_at updated
      ⇒ is_new == False  →  alert block never runs

      Even if it did:  idempotency_key = sha256("4471:new:email:v1")
                       → ON CONFLICT DO NOTHING → 0 rows

[12] 🚫 NO SECOND ALERT.  canonical_jobs #4471 now has 2 job_sources.
──────────────────────────────────────────────────────────────────────
[13] 2026-09-14  job absent from 2 consecutive successful runs
      (jobs_fetched=487 > 50% of 494 ✓, status=success ✓, non-empty ✓)
      → status='closed', job_events 'closed', NO alert
[14] 2026-09-20  reappears → status='reopened' → ✅ ALERT (flagged REOPENED)
```

---

## 28. Answers to Your Research Questions

**A. Can we realistically scrape all 114 career pages?**
**No — and you shouldn't try.** 98/114 (86%) are reachable through legitimate public APIs. The other 16
break down as: 6 blocked by design (Apple 401, Google/Meta/ByteDance JS-only, TikTok 405, Tesla Akamai
403 on everything), 3 acquired (Loom→Atlassian, Neon→Databricks, Superhuman→Grammarly), 6 with no
machine-readable route (Snyk, Deel, Bolt, HubSpot, Cisco, IBM), 1 unverified (Microsoft). The 6 blocked
ones are covered second-hand by the GitHub feeds.

**B. Can most companies be handled by a few ATS connectors?**
**Yes — 84.2% via 7 generic connectors; 80.7% via just three** (Greenhouse 59, Ashby 29, Lever 4).

**C. Which companies require custom scrapers?**
Amazon (JSON), Intuit (TalentBrew), Hudson River Trading (talent-community-only board), Cisco (Phenom,
uncertain), IBM (SPA, uncertain). **Don't build:** Apple, Google, Meta, Tesla, TikTok, ByteDance.

**D. Which job boards can realistically be monitored?**
Only the **GitHub repositories** — Simplify's `listings.json` (30-min, structured) and speedyapply's two
repos (daily, markdown). That's the complete list.

**E. Which should NOT be directly scraped, and why?**
**LinkedIn** (robots.txt explicitly prohibits automated access; hiQ paid $500k on the contract claim),
**Indeed** (`/graphql` and `/api/*` disallowed; Publisher API dead since 2023), **Handshake** (allowlist
robots excluding job pages; EDU API is institution-only), **Jobright** (`/api/` disallowed), **Tesla**
(403 on everything including robots.txt). **Alternative for all of them:** read the underlying ATS
directly — these boards are aggregating the same Greenhouse/Ashby/Lever postings you can already access
at the source, first-hand and fresher.

**F. What is the cheapest reliable architecture?**
One Hetzner CX22 VPS (~$4.10/mo) running a single Python 3.12 process: httpx + APScheduler + SQLite +
SQLAlchemy in Docker, with free-tier Resend, Telegram, Sentry and Healthchecks.io. **≈$4–6/month.**

**G. How often should each source be checked?**
Tier1/Big-Tech ATS 15 min · Tier2 30 min · Tier3 2 h · Workday/Eightfold (no ETag) 60 min · Simplify
20 min · speedyapply **1×/day at 12:15 UTC** (its cron is `0 12 * * *`). Multiply by 3–4× off-season.
ETags make the frequent polls nearly free.

**H. How do we guarantee no duplicate alerts?**
`UNIQUE(idempotency_key)` on `alerts`, where the key is
`sha256(canonical_job_id:alert_type:channel:v1)` — deliberately independent of run id and timestamp —
combined with `INSERT … ON CONFLICT DO NOTHING`, `UNIQUE(source_id, source_job_id)` on `job_sources`,
and job+alert writes committed in one transaction. The guarantee lives in the database, not in
application logic, so it survives crashes, retries and concurrent runs.

**I. How do we identify the same job across different sources?**
The five-level cascade in §9.4. It works because Simplify's `url` field carries the company's real ATS
URL, so L1 (normalized URL) and L2 (ATS-native id) catch nearly everything deterministically.
`_is_distinct_ats_posting` prevents merging two genuinely different requisitions.

**J. How do we detect newly posted jobs?**
L0 miss on `(source_id, source_job_id)` ⇒ new listing; full dedup miss ⇒ new *canonical* job.
Corroborated by `first_published`/`publishedAt`/`createdAt` where the ATS provides it. Greenhouse also
gives `updated_at` on 100% of rows (verified 496/496); Ashby and Lever don't, so those use `content_hash`.

**K. How do we handle deleted/closed jobs?**
A set-difference sweep with three guards (§10.3): only after a **successful**, **non-empty** run with
**no >50% cliff drop**, and only after **2 consecutive** misses. This matters concretely — Snyk, Deel,
Bolt and HubSpot all return HTTP 200 with an empty array, which a naive sweep would read as "everything
closed." For Simplify, the `active` flag is authoritative and no sweep is needed. Closed → no alert;
reopened → alert.

**L. How do we know a scraper silently broke?**
Four independent signals: (1) Pydantic schema validation failure on any field change; (2)
`last_success` staleness > 6× the interval; (3) the anomaly guards — empty-200, cliff drop, payload
explosion, 14-day zero-relevant streak; (4) a **Healthchecks.io dead-man's switch** that alerts when the
heartbeat *stops* — the only monitor that survives the whole process dying.

**M. How much maintenance?**
**~1–2 hours/month in steady state**, concentrated in three recurring tasks: fixing 1–3 slug/config
drifts (companies switch ATS or get acquired — three of your 114 already have), reviewing the weekly
health digest, and adding/removing companies. Expect a **3–5 hour spike each August–September** as
season-specific boards open. The design keeps this low because config changes — not code changes — fix
most breakages.

---

## 29. Top 10 Highest-Risk Assumptions to Validate First

Ranked by (probability of being wrong) × (cost of being wrong).

| # | Assumption | Risk if wrong | How to validate (before writing the connector) |
|---|---|---|---|
| **1** | Simplify's `listings.json` stays on `dev` at that path, structured and 30-min fresh | **Critical** — sole coverage for Apple/Google/Meta/Tesla/TikTok/ByteDance | Log its ETag + record count every poll for 7 days; alert on schema drift. Have the speedyapply parser as the standby. |
| **2** | Public ATS APIs tolerate 15-min polling from one IP across ~100 boards | **Critical** — the whole ingestion model | Run 48h at target cadence *before* building alerts; watch for 429/403. Back off to 30 min at the first sign. |
| **3** | Normalized-URL + ATS-id dedup actually collapses cross-source dupes | **High** — duplicate alerts are the #1 failure you named | Offline test **now**: intersect `listings.json` URLs against live Greenhouse/Ashby/Lever URLs and measure the true match rate. |
| **4** | Deterministic rules generalize beyond my 7,260-title sample | **High** — missed internships are invisible failures | Re-run the corpus across all 92 companies; hand-label 200 early-career titles; require ≥95% recall. |
| **5** | The 15 verified Ashby/Greenhouse slugs are the *right companies* | **High** — silent wrong-company data | I found 3 collisions (`greenhouse/watershed`, `lever/neon`, `greenhouse/coherehealth`). Assert `company_name` in the payload matches config on every run. |
| **6** | Ashby boards returning `jobs:[]` are config, not a transient outage | Medium — 4 companies wrongly written off | Re-probe Snyk/Deel/Bolt/HubSpot weekly for 4 weeks before declaring them permanent gaps. |
| **7** | Greenhouse `updated_at` reliably signals *material* change | Medium — update-alert noise | Sample 50 jobs where `updated_at` moved; check whether `description_hash` also changed. |
| **8** | The guarded closed-sweep never mass-closes | Medium — reopen-alert storm | Chaos test: force a source to return `[]`, a 50% subset, and a 500. Assert zero closures in all three. |
| **9** | Microsoft is on Eightfold and reachable | Low-Medium — 1 company | Probe `apply.careers.microsoft.com` from the deploy host (it failed TLS from mine — could be egress, not the endpoint). |
| **10** | Resend free tier (100/day) exceeds peak alert volume | Low — dropped alerts in peak season | 522 active Summer-2027 listings exist *today*; a bad filter could burst. Enforce `max_per_hour` and make Telegram (unlimited) the primary channel. |

**Validate #1–#5 before Phase 2.** Each is a half-day script, and each can invalidate a design decision
that would otherwise be expensive to unwind.

---

## 30. "If I were building this system, this is exactly how I would build V1"

One Python 3.12 process in Docker on a €3.79 Hetzner box. SQLite through SQLAlchemy so the move to
Postgres is a connection string. APScheduler in-process — no Redis, no Celery, no broker.

Four connectors, not a hundred: **Greenhouse, Ashby, Lever, and Simplify's `listings.json`**. Those four
cover ~100 of your 114 companies, and three of them are the same 40-line pattern — fetch JSON with an
ETag, validate with Pydantic, map to `NormalizedJob`. Companies live entirely in `companies.yaml`
generated from the 114 verified rows I've already written to `research/source_inventory.json`; adding a
company is a config edit, never a code change.

Every fetch stores its raw gzipped payload before parsing, so when a career site changes shape you
replay history against the fixed parser instead of discovering you lost a week of data.

Relevance runs **before** dedup, because deterministic title rules kill 98.4% of rows (measured, not
guessed) and there's no reason to make the expensive stage do 60× the work. No LLM in V1 — log the ~0.5%
ambiguous cases and let real data tell you what the prompt should say.

Dedup keys on normalized application URL and ATS-native job ID, in that order. This works only because
Simplify's feed carries real ATS URLs — which is why that repo is a first-class source and not an
afterthought. No embeddings: you have the requisition ID; a false merge silently costs you a job, and
that trade is strictly worse than an occasional duplicate.

Alerts go through an outbox table with `UNIQUE(idempotency_key)` and `ON CONFLICT DO NOTHING`, written
in the same transaction as the job. The "run it twice, get one email" guarantee is a database
constraint, not a code path — because code paths have bugs and constraints don't.

Telegram for instant push, email for the daily digest. Healthchecks.io as the dead-man's switch, because
every other monitor in the system dies with the process.

**And I would not build:** a LinkedIn scraper, an Indeed scraper, a Handshake integration, a headless
browser, a proxy pool, or a vector database. Each is either legally hostile, structurally unstable, or
solves a problem this design doesn't have. The companies behind those walls are already covered — through
their own ATS, or through a GitHub repo that a company publishes precisely so people like you can read it.

---

## 31. Coding Task Sequence (execute in this order after approval)

```
── VALIDATION SPIKES (do these first — throwaway scripts, ~1 day total) ────────
 0.1  Cross-match listings.json URLs against live Greenhouse/Ashby/Lever URLs
      → measures the REAL dedup hit rate            [validates risk #3]
 0.2  Poll 10 boards at 15-min cadence for 48h, log every status code
                                                     [validates risk #2]
 0.3  Re-run the title-rule corpus across all 92 companies; hand-label 200
                                                     [validates risk #4]
 0.4  Assert payload company_name == config for all 92 slugs
                                                     [validates risk #5]

── PHASE 1 · FOUNDATION ────────────────────────────────────────────────────────
 1.1  Scaffold repo: pyproject, ruff, mypy, pytest, pre-commit, Dockerfile
 1.2  pydantic-settings config + YAML loaders
 1.3  Generate config/companies.yaml from research/source_inventory.json
 1.4  NormalizedJob / Location / Compensation Pydantic models
 1.5  SQLAlchemy models for the §12 schema + Alembic initial migration
 1.6  structlog JSON logging + run-context binding

── PHASE 2 · CONNECTOR FRAMEWORK ───────────────────────────────────────────────
 2.1  BaseConnector: httpx async, ETag store, tenacity retries, timeouts,
      per-host rate limit, circuit breaker, raw_payloads capture
 2.2  Connector registry + scraper_runs recorder
 2.3  GreenhouseConnector + recorded fixtures + tests
 2.4  AshbyConnector    (handle domain-style slugs: 'kraken.com', 'mistral.ai')
 2.5  LeverConnector    (honour Crawl-delay: 1)
 2.6  CLI: `verify-sources` — probe every configured source, report health

── PHASE 3 · COVERAGE ──────────────────────────────────────────────────────────
 3.1  Enable all 92 ATS companies via config; compare counts to §3 baselines
 3.2  Quarantine + report mismatches; fix slugs

── PHASE 4 · GITHUB ────────────────────────────────────────────────────────────
 4.1  SimplifyConnector: raw.githubusercontent + ETag + streaming JSON parse
 4.2  Company alias table + URL→company_id resolution (URL first, name second)
 4.3  Map active/is_visible/terms/sponsorship → lifecycle + filter fields

── PHASE 5 · DEDUPLICATION ─────────────────────────────────────────────────────
 5.1  normalize_url() incl. boards↔job-boards host aliasing + param stripping
 5.2  ats_identity() extractor for all 5 URL patterns
 5.3  normalize_title() / canonical_location_set() / fingerprint()
 5.4  resolve_canonical() L0–L3 + _is_distinct_ats_posting guard
 5.5  ★ Test: Anthropic job via Greenhouse + Simplify → 1 canonical, 2 sources

── PHASE 6 · RELEVANCE ─────────────────────────────────────────────────────────
 6.1  Lexicons incl. the §11.2 traps (placement / campus / recruiter / senior+PhD)
 6.2  Rule stages 0–3 + match_reasons
 6.3  preferences.yaml evaluator (season, location, sponsorship, degree)
 6.4  Corpus regression test (≥99% agreement, all 5 traps handled)

── PHASE 7 · ALERTS ────────────────────────────────────────────────────────────
 7.1  alerts outbox + idempotency key + ON CONFLICT DO NOTHING
 7.2  Alert renderer (§13.3) with official-URL ranking
 7.3  Telegram sender; 7.4 Resend email sender; quiet hours + max_per_hour
 7.5  ★ Test: run pipeline twice → exactly one alert row, one send

── PHASE 8 · LIFECYCLE & MONITORING ────────────────────────────────────────────
 8.1  Guarded closed-sweep + chaos tests (empty / 50% / 500)
 8.2  job_events writer + state machine
 8.3  Health rollup query + staleness alerts + Healthchecks.io heartbeat
 8.4  Daily digest email; Sentry wiring

── PHASE 9 · PRODUCTION ────────────────────────────────────────────────────────
 9.1  docker-compose + healthcheck + restart policy
 9.2  Scheduler intervals, jitter, season profiles
 9.3  Nightly SQLite backup → B2
 9.4  README + docs/RUNBOOK.md + docs/ADDING_A_COMPANY.md
 9.5  7-day unattended soak; confirm zero duplicate alerts

── PHASE 10 · V2 ───────────────────────────────────────────────────────────────
10.1 Workday · 10.2 Eightfold · 10.3 Rippling · 10.4 Amazon · 10.5 Intuit
10.6 speedyapply parsers (adds salary)
10.7 LLM classifier for the ambiguous 0.5%, cached by description_hash
10.8 L4 fuzzy dedup · 10.9 Postgres migration · 10.10 Discord + web UI
```

---

*End of report. Nothing has been implemented — `research/` contains this document, the verified
`source_inventory.json` (114 rows), and the reproducible probe scripts.*
