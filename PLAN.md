# Job Alerts — Build Plan (v1)

Based on `research/RESEARCH_REPORT.md` (probed 2026-08-20). This file adds four things the
research left out: **LinkedIn/board coverage**, **job descriptions for every job**, a
**US-citizenship filter**, and **closing the 6 company gaps**. I checked the facts behind these on 2026-09-22.

---

## 1. What we collect per job

| Field | Where it comes from |
|---|---|
| `job_id` | Our own canonical ID (a hash of the ATS identity), plus each source's native ID kept in `job_sources` |
| `title`, `company_name` | Every source provides them |
| `description` | Ashby and Lever include it in the list call. For Greenhouse, fetch `/jobs/{id}` **for new IDs only**. For jobs found through Simplify, follow the `url` to the ATS and fetch it there. For Big Tech (Google, Apple, Meta, Tesla, TikTok) we get **no description** because their sites block automated access. Those alerts are marked "description unavailable". |
| `apply_url`, `locations`, `posted_at` | Every source provides them |

---

## 2. Sources: what works and what doesn't

| Source | Can we? | How |
|---|---|---|
| **Company ATS APIs** (Greenhouse 59, Ashby 29, Lever 4, Workday, Eightfold, Rippling, Amazon) | ✅ | Official public JSON, no login. 98 of 114 companies. |
| **GitHub lists**: SimplifyJobs `listings.json`, speedyapply SWE+AI | ✅ | `raw.githubusercontent.com` with ETags. Covers Apple, Google, Meta, Tesla, TikTok, ByteDance and about 700 other companies. |
| **LinkedIn** | ❌ Scraping is banned (robots.txt, and the *hiQ* case ended in a $500k judgment) | ✅ **Workaround: parse LinkedIn job-alert emails.** Set up saved searches on LinkedIn → alerts arrive in a dedicated Gmail inbox → the Gmail API reads them. This is legitimate (it's your own mail) and gives title, company, location and the LinkedIn job ID. |
| **Indeed / Glassdoor / Handshake / Jobright / ZipRecruiter** | ❌ Scraping is banned or needs a login | ✅ **Same email-alert workaround.** Every one of them sends job-alert emails. |
| **Google Jobs (SerpApi)** / **Adzuna API** | 🟡 Optional | Paid or free-tier official APIs. Useful for companies outside our list. |
| **6 gap companies** (Snyk, Deel, Bolt, HubSpot, Cisco, IBM) | ❌ No public API | ✅ Sign up for each company's **own career-site job-alert email** (all 6 offer it) and parse those emails. Also check the Simplify feed and Schema.org `JobPosting` on their job pages. |

**Email-parsing caveat:** alert emails usually include only the title, company, location and a
link, with no description. For a LinkedIn job we try to find the same job at the company's ATS
(see §3). If we find it, we have the description. If we don't, the alert says "open on LinkedIn".

---

## 3. Deduplication (the same job on LinkedIn and on the company site shows up once)

The matching cascade stops at the first match:

1. **Same source and same native ID.** We've already seen this listing.
2. **Same normalized apply URL.** Tracking parameters are stripped and `boards.`/`job-boards.greenhouse.io` are treated as one host. This catches almost all ATS↔Simplify duplicates, because Simplify links straight to the ATS.
3. **Same ATS identity parsed from the URL,** e.g. `(greenhouse, anthropic, 5391376008)`.
4. **Fingerprint:** company + normalized title + location + season.
5. **Fuzzy match for email and board sources:** same company, title similarity ≥ 92, overlapping location, posted within 21 days.
   - This is the step that merges a **LinkedIn email job with the company-site job**. LinkedIn emails carry no ATS URL, so the match has to be fuzzy.
   - Two jobs that each have their own ATS requisition ID are **never** merged.

**One alert per canonical job,** enforced by a `UNIQUE(idempotency_key)` constraint in the DB.
If LinkedIn reports a job we already alerted on, we only add a source row. No second notification.

---

## 4. US-citizenship filter (new; the research assumed the user was a US citizen)

**Finding:** Simplify's `sponsorship` field is useless for this filter. Of 4,531 active listings,
4,510 are set to `"Other"` and only 5 say `"U.S. Citizenship is Required"`. **We have to read the
description.** A sample of live ATS data shows how uneven the wording is:

| Company | Descriptions mentioning citizenship, clearance or export control |
|---|---|
| Shield AI | 460 / 525 |
| Palantir | 258 / 312 |
| OpenAI | 43 / 817 (the Gov/Security roles) |
| Ramp | 0 / 151 |

The filter has three tiers:

1. **Hard reject** (regex): "must be a U.S. citizen", "U.S. citizenship is required", "active
   (Secret/TS) clearance required", "ability to obtain a security clearance", "ITAR … U.S. person".
   Simplify `sponsorship == "U.S. Citizenship is Required"` is also a hard reject.
2. **Ambiguous** (export-control boilerplate, "U.S. person" without a requirement verb): one
   Haiku LLM call, cached by description hash → `{requires_citizenship: bool, reason}`.
3. **Unknown** (no description, e.g. Big Tech via GitHub or LinkedIn email): **alert anyway**
   with the tag `⚠ citizenship not verified`, so no job is silently dropped.
- Optional company-level default: flag defense or government contractors (Anduril, SpaceX,
  Shield AI, Palantir) as "likely citizenship". These are config values, not code.
- **Decide:** should we also drop jobs that say "no visa sponsorship"? It's a config switch
  (`drop_no_sponsorship: true/false`).

Filters run in this order: relevance by title (drops ~98% of postings) → dedup → fetch the
description → citizenship check → alert. Descriptions are fetched only for the few jobs that survive.

---

## 5. Where notifications go

| Channel | Use | Cost |
|---|---|---|
| **Telegram bot** | Instant push to your phone for every new relevant job | Free |
| **Email (Resend or Gmail SMTP)** | Daily 08:30 digest: new jobs, updated jobs, and system health | Free (3k/mo) |
| Discord webhook | Optional searchable archive channel | Free |

Each alert shows: company, title, job ID, location, a short snippet of the description, the
citizenship status, which sources saw the job, and an **Apply link that always points to the company's ATS** (not LinkedIn).

---

## 6. Fetch frequency (peak season Aug–Nov; slower off-season)

| Source | Peak | Off-season |
|---|---|---|
| Tier 1 and Big Tech ATS (ETag, usually 304 = free) | 15 min | 60 min |
| Tier 2 ATS | 30 min | 2 h |
| Tier 3 ATS | 2 h | 6 h |
| Workday / Eightfold / Amazon (no ETag) | 60 min | 3 h |
| Simplify `listings.json` | 20 min (updates every 30 min) | 60 min |
| speedyapply | once a day, 12:15 UTC | once a day |
| **Gmail alert inbox** (LinkedIn, Indeed, Handshake, gap companies) | 10 min | 30 min |

That comes to about 10k requests a day, mostly 304s. Requests are jittered, with at most 8 at a time overall and 2 per host.

---

## 7. Resources needed

| Item | Why | Cost |
|---|---|---|
| Small VPS (Hetzner CX22 / $6 DO) | Runs one Python process with SQLite | ~$4–6/mo |
| GitHub personal access token | 5,000 req/hr instead of 60 | Free |
| Telegram bot token and your chat ID | Push alerts | Free |
| **Dedicated Gmail account and Google Cloud OAuth client** (Gmail API, read-only) | Email-alert ingestion | Free |
| LinkedIn, Indeed, Handshake and company-career alert subscriptions sent to that Gmail | Board coverage | Free |
| Anthropic API key (Haiku) | Ambiguous relevance and citizenship calls, a few a day | < $1/mo |
| Resend API key (or Gmail SMTP) | Digest email | Free |
| Healthchecks.io | Alerts you if the system stops running | Free |
| Optional: SerpApi / Adzuna | Companies outside our list | $0–25/mo |
| **Total** | | **≈ $5–8/mo** |

Stack: Python 3.12, httpx (async), Pydantic, SQLAlchemy and SQLite, APScheduler, rapidfuzz, Docker Compose.

---

## 8. Build order (~3 weeks part-time)

1. Foundation: config (`companies.yaml` from `research/source_inventory.json`), DB schema, `NormalizedJob`.
2. Greenhouse, Ashby and Lever connectors (92 companies) and a description fetcher for new IDs only.
3. Simplify connector (covers Big Tech) and description follow-through to the ATS URL.
4. Dedup cascade L0–L3 and the idempotent alert outbox → Telegram.
5. Relevance rules and the **citizenship filter** (regex tiers + Haiku for ambiguous cases).
6. **Gmail alert-email ingester:** a parser each for LinkedIn, Indeed, Handshake and the gap companies' emails; fuzzy L4 dedup.
7. Lifecycle (closed/reopened, with guards against empty 200 responses), daily digest, health checks.
8. Workday, Eightfold, Rippling, Amazon and speedyapply connectors → deploy to the VPS.

**Never build:** LinkedIn or Indeed scrapers, CAPTCHA or anti-bot bypass, proxy rotation, headless-browser scraping.
