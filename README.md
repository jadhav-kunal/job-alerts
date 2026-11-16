# job-alerts

Posts new **early-career software, AI/ML, research, data and quant roles** (internships + new grad /
entry-level) to Discord within minutes of them going up. It can also make a tailored resume and cover letter for a
job (with Claude Code), and it comes with a browser extension that fills in application forms for you.

```
120 sources ──► dedup (URL → ATS id → fingerprint) ──► title rules ──► description ──► citizenship / clearance
            ──► years + contract rules ──► outbox ──► Discord, one channel per company tier
 98 company ATS boards   (Greenhouse 57, Ashby 32, Lever 4, Workday 2, Amazon, Netflix, Rippling)
  4 GitHub lists, JSON   (SimplifyJobs internships + new grad; vanshb03 internships + new grad)
  2 GitHub lists, tables (speedyapply/2027-SWE-College-Jobs internships + new grad)
 15 VC portfolio boards  (Getro: Accel, General Catalyst, Thrive, Lux, 8VC, Menlo, Redpoint, …)
  1 a16z portfolio board (Consider) + Dover's public job board (every startup hiring through Dover)
```

The aggregator sources, the years/contract rules and some citizenship wording were adapted from
[jobhunter](https://github.com/jovin-nicholas/jobhunter) (MIT).

You can set it up in three levels. Each one builds on the one before, so stop wherever you like:

| Level | What you get | Needs |
|---|---|---|
| **1. Alerts** | Job alerts in Discord | Python 3.12 (or Docker) and a Discord webhook. ~5 min |
| **2. Bot** | Applied / Later / Skip buttons on alerts, `/todo`, per-tier channels | A Discord bot. ~10 min |
| **3. Claude + extension** | 📄 tailored resume, ✉️ cover letter, browser extension that fills application forms, ✍️ AI answers to essay questions | [Claude Code](https://claude.com/claude-code) (logged in), a TeX install, Chrome or Brave, your resume in LaTeX. ~30 min |

---

## Level 1: Alerts

### 1. Get the code and install

```bash
git clone https://github.com/jadhav-kunal/job-alerts.git ~/job-alerts
cd ~/job-alerts

# with uv (https://docs.astral.sh/uv/):
uv venv -p 3.12 .venv && uv pip install --python .venv/bin/python -e '.[dev,bot]'
# or plain pip:
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev,bot]'

cp .env.example .env
cp config/profile.example.yaml config/profile.yaml     # fill in later (level 3); fine to leave empty for now
```

`.env` and `config/profile.yaml` hold your secrets and personal details. They are in `.gitignore`. Never commit them.

### 2. Make a Discord webhook

1. Make a Discord server for yourself (or use one you own), and a channel such as `#job-alerts`.
2. **Server Settings → Integrations → Webhooks → New Webhook**, pick the channel, **Copy Webhook URL**.
3. Paste it into `.env`: `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`

### 3. Say what you want

Edit `config/preferences.yaml`. The defaults are new grad + internships, US + remote, in software, AI/ML, research,
data and quant, for the 2027 internship terms. The settings you are most likely to change:

- `roles.levels`: `[intern, new_grad]`, or just one.
- `roles.categories`: any of `software, ai_ml, research, data, quant`.
- `seasons`: internship terms you want, e.g. `[Summer 2027]`. `[]` = any.
- `locations.allow`: add `non_us` to also get international roles.
- `eligibility.citizenship_filter`: `true` drops postings that need US citizenship or a security clearance.
  Set it to `false` if you are a US citizen. `drop_no_sponsorship: true` also drops "no visa sponsorship" postings
  (otherwise they are only tagged 🛂).
- `user_agent`: you can add a contact email for the job boards, e.g. `"job-alerts/1.0 (personal job monitor; contact you@example.com)"`.

More options are under [Tuning](#tuning-configpreferencesyaml).

### 4. Test and run

```bash
.venv/bin/python -m jobalerts test-discord    # a ✅ message should show up in your channel
.venv/bin/python -m jobalerts once --no-send  # one dry pass over every source (takes a few minutes)
.venv/bin/python -m jobalerts run             # the daemon: keep this running
```

**First run:** every source is "seeded". The jobs that already exist are recorded without an alert, except ones
posted in the last 48 h (`alerts.bootstrap_alert_hours`). After that, every newly seen job alerts. Expect ~100
alerts on day one, then a steady trickle.

Or with Docker, no Python needed: `docker compose up -d` (logs: `docker compose logs -f`). See [Deploy](#deploy) for
keeping it running all the time.

---

## Level 2: Discord bot (buttons, `/todo`, tier channels)

Discord only allows clickable buttons on messages a **bot** sends, so this needs a bot of your own.

1. <https://discord.com/developers/applications> → **New Application** → **Bot** → **Reset Token** → copy it.
2. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permissions *View Channels, Send Messages,
   Embed Links, Attach Files, Read Message History* (and *Manage Channels* for step 5). Open the URL and add the
   bot to your server.
3. Discord **Settings → Advanced → Developer Mode** on. Right-click your alerts channel → **Copy Channel ID**.
4. In `.env`: `DISCORD_BOT_TOKEN=…` and `DISCORD_CHANNEL_ID=…`. When both are set, the daemon posts as the bot.
5. Optional, one channel per company tier: `.venv/bin/python -m jobalerts setup-channels` makes a "Job Alerts"
   category with the six channels below and writes their ids into `.env`. You can remove *Manage Channels* afterwards.
6. Restart the daemon (`run`, or `docker compose up -d --build`) and start the bot in a second terminal:
   `.venv/bin/python -m jobalerts bot`

The **bot** handles button clicks, slash commands and the extension's local API. Run it on your own computer, not in
Docker (level 3 needs your `claude` login and TeX). The **daemon** (`run`) can live anywhere, including a VPS.

### Channels: one per tier

| Channel | What lands there |
|---|---|
| `#big-tech` | Meta, Google, Apple, Amazon, Microsoft, NVIDIA, ByteDance/TikTok, Tesla, Salesforce, Intuit, Rippling |
| `#tier-1` | AI labs, quant firms and top startups (OpenAI, Anthropic, Jane Street, HRT, Stripe, Databricks, …) |
| `#tier-2` | Strong tech companies and well-funded startups |
| `#tier-3` | The rest of `config/companies.yaml` |
| `#other-companies` | Every company not in `companies.yaml` (GitHub lists, VC boards, Dover). The busiest channel |
| `#job-alerts-status` | Daily summary and broken-source warnings |

A company's tier comes from `config/companies.yaml`. To move a company, change its `tier` there. Unset channels fall
back to `DISCORD_CHANNEL_ID`. Prefer one intern channel and one new-grad channel? Set `alerts.route_by: level`.
Webhook-only users can do the same with `DISCORD_WEBHOOK_BIG_TECH` … `DISCORD_WEBHOOK_OTHER` in `.env`.

### What an alert contains

Company (and tier), title linked to the **company's own apply page**, location, level, area, internship term,
posted time, pay (when the source gives it), a description snippet, **eligibility** (✅ nothing found, ⚠
export-control or US-person wording, ❔ not verified), 🛂 if the posting says no visa sponsorship, and which sources
saw it. The coloured bar is the area: 🟣 AI/ML · 🔵 Research · 🟢 Software · 🟠 Data · 🔴 Quant · grey other.

### Buttons and `/todo`

| Button | What it does |
|---|---|
| ✅ Applied · ⭐ Later · ⏭ Skip | Records the status in `data/applications.jsonl` and recolours the alert. Click again to undo. |
| Apply | Opens the application page. |
| 📄 Create resume · ✉️ Cover letter | Level 3. |

**`/todo [channel] [days] [include_later]`**: alerts you have not marked Applied or Skip, oldest first. Without a
channel it shows the count per channel. The daily summary also says how many you applied to in the last 24 hours.
Alerts posted before the bot was set up: `.venv/bin/python -m jobalerts upgrade-alerts --days 14` adds the buttons.

---

## Level 3: Claude Code features and the browser extension

### Requirements

- **Claude Code**, installed and logged in: `claude --version` should work in a terminal. Resume, cover letter and
  answer runs use your own Claude plan (a few minutes each).
- **TeX** with `pdflatex` and `pdfinfo`. macOS: `brew install --cask mactex-no-gui` and `brew install poppler`.
  Linux: `texlive-latex-extra` and `poppler-utils`.
- The bot from level 2, running on this machine.
- **Node** (optional): only for the extension's JS tests.

### 1. Fill in your profile

Edit `config/profile.yaml` (copied from `config/profile.example.yaml` in level 1): name, contact, links, address,
education, work history, work authorization, EEO answers, and `default_resume` (path to a PDF of your resume).
Empty answers are never guessed: the extension leaves those questions for you. Restart the bot after editing.

### 2. Install the two Claude skills

Claude Code follows two skills, which live in `~/.claude/skills/`. Templates are in `skills/` in this repo.

**resume-builder** (your resume and experience, used by 📄, ✉️ and ✍️):

```bash
mkdir -p ~/.claude/skills
cp -R skills/resume-builder ~/.claude/skills/resume-builder
```

Then add your own files to `~/.claude/skills/resume-builder/references/`:

| File | What to put there |
|---|---|
| `base-resume.tex` | Your current one-page resume in LaTeX. It must compile with `pdflatex`. (Have an Overleaf resume? Download its `.tex`.) |
| `bullet-library.tex` | Every resume line you could use, including the ones that don't fit on one page: extra bullets per job, more projects, the full skills list. Claude picks from here per job. |
| `context.md` | Your experience bank in plain words: jobs, projects, papers, numbers and what they mean. Start from `context-template.md`. Claude never claims anything that is not in these files. |

Check it: open `claude` in any folder and ask "use the resume-builder skill to tailor my resume to this job: <paste
a posting>".

**application-answers** (rules for answering application questions):

```bash
cp -R skills/application-answers ~/.claude/skills/application-answers
cd ~/.claude/skills/application-answers && mkdir -p references
ln -sf ~/.claude/skills/resume-builder/SKILL.md          references/resume-builder-SKILL.md
ln -sf ~/.claude/skills/resume-builder/references/context.md references/context.md
ln -sf ~/job-alerts/config/profile.yaml                  references/profile.yaml
cd ~/job-alerts
```

(If you cloned somewhere other than `~/job-alerts`, change the last link.)

### 3. Use it from Discord

- **📄 Create resume** on an alert: Claude tailors `base-resume.tex` to that job and posts a one-page PDF back.
  Files are saved in `resumes/<Company>_<Title>_<id>/` (`First_Last_Resume_<Company>.pdf`, `resume.tex`,
  `changes.md`, `job.md`). A second click sends the existing PDF; `/resume <job id> regenerate:True` redoes it.
- **✉️ Cover letter**: a one-page letter from your experience bank, laid out with `config/cover_letter_template.tex`.
  If you keep earlier letters as `~/Documents/Cover_Letter___*.pdf` or `~/Downloads/Cover_Letter___*.pdf`, Claude
  matches their voice. `/cover <job id>` does the same.
- Terminal, no Discord: `.venv/bin/python -m jobalerts resume <job id>` (the id is in the alert's footer, `job #27662`).
- Settings live under `resume:` in `config/preferences.yaml` (output folder, file name prefix, model, timeout,
  concurrency).
- If the bot or the computer is off, Discord shows "This interaction failed". Click again once it is running.

### 4. Install the browser extension

`extension/` is a Chrome/Brave extension. It fills an application form from `config/profile.yaml`, attaches the job's
tailored resume (or `default_resume`) and cover letter, and marks the alert ✅ Applied when the site shows its
"application received" page. **It never presses Submit.**

1. Make sure the bot is running (`.venv/bin/python -m jobalerts bot`). On first start it creates
   `data/helper_token`, a random password the extension uses to talk to the bot.
2. Chrome: `chrome://extensions` (Brave: `brave://extensions`) → turn on **Developer mode** (top right) →
   **Load unpacked** → choose the `extension` folder of this repo.
3. On the extension's card: **Details → Extension options**. Paste the token:
   - macOS: `cat ~/job-alerts/data/helper_token | pbcopy`, then paste.
   - Linux: `cat ~/job-alerts/data/helper_token` and copy the output.

   Click **Save and test**. You should see "✅ Connected".
4. Optional: pin the extension (puzzle-piece icon → pin) so its toolbar button is one click away.

**Using it.** Open a job's application page. On Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, iCIMS,
Dover, Gem, Breezy, BambooHR and Rippling a panel appears bottom-right; on any other site click the extension's
toolbar icon.

- **Fill form**: fills everything `profile.yaml` covers and attaches files. Green outline = filled, orange = needs
  you (essays, questions your profile leaves empty, dropdowns it could not settle).
- **✍️ Answer the rest**: sends the remaining questions (essays, "why this company", program-specific yes/no) to
  Claude Code with the posting, your experience bank and profile. A minute or two later the answers appear outlined
  in blue. It answers only from your files, leaves a question empty when it cannot answer truthfully (the panel says
  why), keeps to the form's length limits, and never touches salary, EEO, consent or anything `profile.yaml` covers.
- The panel can also start a tailored resume or cover letter for that job and attaches it when ready.
- Always read everything over, then press Submit yourself.
- Workday: sign in first; its custom widgets only partly fill.

How it connects: the bot serves a small API on `127.0.0.1:8765` (`jobalerts/helper.py`), only on your own machine
and only for requests carrying the token. Changed the port in `preferences.yaml` (`helper.port`)? Set the same port in
the extension options.

Updating the extension after a `git pull`: `chrome://extensions` → the extension's ↻ reload button.

---

## Commands

| | |
|---|---|
| `python -m jobalerts run` | Daemon. Polls each source on its schedule and drains the outbox every 20 s |
| `python -m jobalerts once [--source ashby:openai] [--no-send]` | One pass (all sources or a substring match) |
| `python -m jobalerts test-discord` | Posts a test message to each configured channel |
| `python -m jobalerts setup-channels` | Creates the tier channels (bot needs **Manage Channels**) and saves their ids in `.env` |
| `python -m jobalerts explain "ML Engineer, New Grad" -l "Seattle, WA"` | Shows why a title would or would not match |
| `python -m jobalerts recent -n 30` | Latest relevant jobs in the DB |
| `python -m jobalerts stats` | Counts, top reject reasons, failing sources |
| `python -m jobalerts bot` | The Discord bot: buttons, `/todo`, `/resume`, `/cover`, and the extension's local API |
| `python -m jobalerts upgrade-alerts` | Gives already-posted alerts the current buttons |
| `python -m jobalerts resume <job id>` | Tailored resume PDF for one job, from the terminal |
| `.venv/bin/python -m pytest` | The test suite |

(Use `.venv/bin/python` in place of `python` unless the venv is activated.)

## Tuning (`config/preferences.yaml`, then restart)

- `roles.levels` / `roles.categories`: which levels and areas you get.
- `roles.accept_unleveled: true`: also get titles with no level ("Research Engineer"). Noisy at the AI labs.
- `seasons`: internship terms you want (default: the 2027 terms).
- `locations.allow`: add `non_us` to get international roles too.
- `eligibility.citizenship_filter` / `drop_no_sponsorship`: see Level 1. Clearance wording is read per sentence:
  "Requires an active Secret clearance", "TS/SCI" or "must be eligible for a clearance" drops the job;
  "clearance is a plus" only warns.
- `filters.max_years_required` (2): new-grad roles asking for more years get a "⚠ asks for 3+ years" heads-up.
  `years_action: drop` drops them instead.
- `filters.employment_exclude` ([contract, hourly]): drops contract roles and hourly pay. Internships and
  contract-to-hire are kept by default.
- `sources.getro.collections` / `consider.boards` / `markdown_lists` / `dover`: the aggregator sources; remove one to
  turn it off.
- `sources.season_profile`: `peak` from Aug to Nov, `normal` or `quiet` off-season (2× or 4× slower polling).
- Add a company: add an entry to `config/companies.yaml`, or add it to `OVERRIDES` in `scripts/gen_companies.py` and
  regenerate the file.

## Deploy

A laptop that sleeps polls nothing (macOS idle sleep paused the daemon for 20 minutes in testing). Options:

- **VPS (recommended, ~$5/mo):** copy the folder, fill in `.env`, run `docker compose up -d`. SQLite is in `./data`.
  Run the bot (level 2/3) on your own computer.
- **Docker on your computer** (`docker compose up -d`) works but pauses while the computer sleeps. While the
  container is up, run CLI commands **inside** it: `docker compose exec jobalerts python -m jobalerts stats`.
  On macOS, never run `once`/`run` on the host while the container is running: two writers across the Docker VM
  boundary can corrupt the DB.
- **Always-on Mac:** `deploy/com.jobalerts.plist` (daemon) and `deploy/com.jobalerts.resumebot.plist` (bot) are
  launchd jobs that start at login and restart on crash. First replace the placeholder user name and, if needed,
  the project path:
  ```bash
  sed -i '' "s/YOUR_USERNAME/$USER/g" deploy/*.plist
  cp deploy/com.jobalerts.resumebot.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.jobalerts.resumebot.plist
  ```
  (Don't commit the edited plists.)
- Set `HEALTHCHECK_URL` in `.env` ([healthchecks.io](https://healthchecks.io)) to get an email if the daemon stops.

## Troubleshooting

- **No alerts:** `python -m jobalerts stats` shows failing sources and the top reject reasons;
  `python -m jobalerts explain "<title>" -l "<location>"` shows why one title is filtered.
- **"This interaction failed" in Discord:** the bot is not running.
- **Extension says not connected:** the bot is not running, or the token in the options does not match
  `data/helper_token`.
- **Resume button fails with "base-resume.tex not found":** the resume-builder skill is not at
  `~/.claude/skills/resume-builder/` or its `references/base-resume.tex` is missing.
- **"`claude` CLI not found":** install Claude Code and make sure `claude` is on your PATH (`~/.local/bin` is checked).
- **Bot logs:** the terminal running `bot`, or `data/resumebot.log` under launchd. Extension logs: `data/extension.log`.

## Privacy

Everything personal stays on your machine and out of git: `.env` (tokens, webhooks), `config/profile.yaml` (your
answers), `data/` (job DB, application log, extension token) and `resumes/`. Your resume and experience bank live in
`~/.claude/skills/`, outside the repo. If you fork this, check `git status` before committing.

## Status vs PLAN.md

| Plan item | Status |
|---|---|
| Greenhouse / Ashby / Lever / Workday / Amazon / Eightfold / Rippling connectors | ✅ |
| Simplify feeds for Big Tech | ✅ Internships **and** new grad |
| Dedup cascade, idempotent outbox | ✅ `UNIQUE(idempotency_key)`, tested |
| Citizenship filter | ✅ Regex tiers, title check, Simplify field, defense-company flag. Ambiguous cases alert with ⚠ |
| Discord delivery, daily summary, circuit breaker, health pings | ✅ |
| speedyapply lists, VC portfolio boards (Getro, a16z), Dover | ✅ |
| Gmail ingestion, LLM citizenship check, closed/reopened lifecycle | ❌ Not built |
| Microsoft direct | ❌ Eightfold API returns 403, so Microsoft comes through the Simplify lists only |
