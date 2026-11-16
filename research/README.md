# Research Phase Output — 2027 Internship Job Monitor

**No production code has been written.** This directory is the Phase 0 deliverable.

| File | What it is |
|---|---|
| `RESEARCH_REPORT.md` | The full research report + implementation plan (31 sections) |
| `source_inventory.json` | **114 verified company→ATS rows** — the seed for `config/companies.yaml` |
| `build_inventory.py` | Generates `source_inventory.json`; prints coverage stats |
| `probes/` | Reproducible probe scripts used to gather the evidence |

## Reproducing the evidence

```bash
python3 probes/probe_ats.py      # sweep 6 ATS APIs across all companies
python3 probes/fingerprint.py    # detect ATS from live career-page HTML
python3 probes/extract_slug.py   # extract exact board slugs from page source
python3 probes/verify_slugs.py   # confirm each slug returns real job data
python3 probes/robots.py         # pull robots.txt from every candidate source
python3 build_inventory.py       # rebuild inventory + coverage stats
```

All probes are read-only GETs with an identifying User-Agent and modest concurrency.

## Headline numbers (verified 2026-08-20)

```
114 target companies
 98 (86.0%) reachable via public APIs today
 96 (84.2%) via 7 generic ATS connectors
 92 (80.7%) via just THREE: Greenhouse (59) · Ashby (29) · Lever (4)
  6 blocked → covered by the Simplify GitHub feed
  6 true gaps · 3 acquired · 1 unverified
```

## Status legend used in `source_inventory.json`

`VERIFIED` endpoint returned real job data · `PARTIAL` reachable but incomplete ·
`LIKELY` strong indirect evidence · `UNCERTAIN` needs a human check ·
`NO_API` board exists but returns no data · `BLOCKED` auth/JS/anti-bot wall ·
`DO_NOT_SCRAPE` explicit refusal · `ACQUIRED` company no longer independent
