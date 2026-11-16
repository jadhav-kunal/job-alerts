"""CLI.

  python -m jobalerts run                 # daemon: poll on schedule, post to Discord
  python -m jobalerts once [--source K]   # one pass over every (or one) source, then send
  python -m jobalerts test-discord        # post a test message to each configured webhook
  python -m jobalerts setup-channels      # create the tier channels (bot mode) and save their ids in .env
  python -m jobalerts upgrade-alerts      # give already-posted alerts the current buttons (Applied/Later/Skip/…)
  python -m jobalerts explain "Title" [-l "City, ST"]   # why would this title match / not match?
  python -m jobalerts recent [-n 20]      # latest relevant jobs in the database
  python -m jobalerts stats               # source health + counts
  python -m jobalerts bot                 # resume bot: handles "📄 Create resume" clicks (run on the host)
  python -m jobalerts resume 123          # make the tailored resume for job #123 from the terminal
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import signal
import time

import httpx

from . import config, discord
from .db import Store
from .http import Http
from .models import NormalizedJob
from .pipeline import Pipeline
from .relevance import classify

log = logging.getLogger("jobalerts")


async def _run_batch(pipe: Pipeline, conns) -> None:
    results = await asyncio.gather(*(pipe.run_source(c) for c in conns))
    for r in results:
        if r.status == "failed":
            log.warning("%-40s FAILED %s", r.source, r.error)
        elif r.new_jobs or r.status == "ok":
            log.info("%-40s %-12s fetched=%-5d new=%-4d relevant=%d", r.source, r.status, r.fetched, r.new_jobs,
                     r.new_relevant)


async def cmd_once(args) -> None:
    s = config.load()
    db = Store(s.db_path)
    http = Http(s.raw["user_agent"])
    try:
        conns = [c for c in s.connectors if not args.source or args.source in c.key]
        if not conns:
            raise SystemExit(f"no source matches {args.source!r}")
        await _run_batch(Pipeline(s, db, http), conns)
    finally:
        await http.close()
    if not args.no_send:
        sent = 0
        while n := await discord.drain(s, db):
            sent += n
        log.info("sent %d Discord alerts", sent)
    pend = db.one("SELECT COUNT(*) FROM alerts WHERE status='pending'")[0]
    if pend:
        log.info("%d alerts pending in the outbox", pend)


async def cmd_run(args) -> None:
    s = config.load()
    db = Store(s.db_path)
    http = Http(s.raw["user_agent"])
    pipe = Pipeline(s, db, http)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    t0 = time.monotonic()
    # Stagger the first pass over ~2 minutes so 100 sources never fire in the same second.
    next_due = {c.key: t0 + random.uniform(0, 120) for c in s.connectors}
    running: set[str] = set()
    hc_url, last_hc = os.environ.get("HEALTHCHECK_URL"), 0.0
    log.info("daemon started: %d sources", len(s.connectors))

    async def one(c):
        running.add(c.key)
        try:
            await _run_batch(pipe, [c])
        finally:
            running.discard(c.key)
            row = db.one("SELECT consecutive_failures FROM sources WHERE key=?", c.key)
            factor = 4 if row and row[0] >= 3 else 1
            next_due[c.key] = time.monotonic() + s.intervals[c.key] * factor * random.uniform(0.9, 1.1)

    tasks: set[asyncio.Task] = set()
    while not stop.is_set():
        t = time.monotonic()
        for c in s.connectors:
            if next_due[c.key] <= t and c.key not in running:
                task = asyncio.create_task(one(c))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        discord.queue_daily_summary(s, db)
        try:
            await discord.drain(s, db)
        except Exception as e:  # noqa: BLE001
            log.warning("drain failed: %s", e)
        if hc_url and time.monotonic() - last_hc > 300:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.get(hc_url)
                last_hc = time.monotonic()
            except httpx.HTTPError:
                pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass
    log.info("stopping; waiting for %d in-flight sources", len(tasks))
    await asyncio.gather(*tasks, return_exceptions=True)
    await http.close()


async def cmd_test_discord(args) -> None:
    s = config.load()
    routes = list(discord.TIER_CHANNELS) if s.alerts.get("route_by", "tier") == "tier" else ["intern", "new_grad", "ops"]
    targets = {r: s.target_for(r) for r in routes}
    if not any(targets.values()):
        raise SystemExit("No webhook set. Put DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... in .env")
    async with httpx.AsyncClient(timeout=20) as client:
        for route, t in targets.items():
            if t:
                mode, dest = t
                await discord.post(client, dest, {"content": f"✅ job-alerts connected ({mode}): `{route}` alerts will land here."},
                                   s.bot_token if mode == "bot" else None)
                print(f"{route}: ok ({mode})")


async def cmd_setup_channels(args) -> None:
    """Creates a "Job Alerts" category with one channel per tier (needs the bot's Manage Channels permission), then
    writes DISCORD_CHANNEL_BIG_TECH … DISCORD_CHANNEL_OPS into .env. Existing channels with the same name are reused."""
    s = config.load()
    if not s.bot_token or not os.environ.get("DISCORD_CHANNEL_ID"):
        raise SystemExit("Needs DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in .env (README → Resume button).")
    api = httpx.AsyncClient(base_url=discord.API, headers={"Authorization": f"Bot {s.bot_token}"}, timeout=20)
    async with api:
        r = await api.get(f"/channels/{os.environ['DISCORD_CHANNEL_ID']}")
        r.raise_for_status()
        guild = r.json()["guild_id"]
        existing = (await api.get(f"/guilds/{guild}/channels")).json()

        async def ensure(name: str, kind: int, **extra) -> str:
            for ch in existing:
                if ch["name"] == name and ch["type"] == kind:
                    return ch["id"]
            r = await api.post(f"/guilds/{guild}/channels", json={"name": name, "type": kind, **extra})
            if r.status_code == 403:
                raise SystemExit("The bot may not create channels. In Discord: Server Settings → Roles → (the bot's "
                                 "role) → turn on Manage Channels, then run this again. Or create the channels "
                                 "yourself and put their ids in .env (see .env.example).")
            r.raise_for_status()
            existing.append(r.json())
            return r.json()["id"]

        category = await ensure(args.category, 4)
        ids = {}
        for pos, (route, (name, topic)) in enumerate(discord.TIER_CHANNELS.items()):
            ids[route] = await ensure(name, 0, parent_id=category, topic=topic, position=pos)
            print(f"#{name:<20} {ids[route]}")
    env_vars = {s.alerts["routes"][r].replace("WEBHOOK", "CHANNEL"): cid for r, cid in ids.items()
                if r in s.alerts.get("routes", {})}
    _write_env(config.ROOT / ".env", env_vars)
    print(f"saved {len(env_vars)} channel ids to .env; restart the daemon (docker compose up -d) to use them")


async def cmd_upgrade_alerts(args) -> None:
    """Edits alerts the bot already posted so they carry the current buttons, and records each one's message id in
    data/jobs/<id>.json (for /todo links and for recolouring from the browser extension)."""
    import json as _json
    from datetime import datetime, timedelta, timezone
    s = config.load()
    if not s.bot_token:
        raise SystemExit("Needs DISCORD_BOT_TOKEN in .env.")
    routes = {os.environ.get(v.replace("WEBHOOK", "CHANNEL")): r for r, v in (s.alerts.get("routes") or {}).items()}
    channels = [c for c in {*routes, os.environ.get("DISCORD_CHANNEL_ID")} if c]
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    api = httpx.AsyncClient(base_url=discord.API, headers={"Authorization": f"Bot {s.bot_token}"}, timeout=30)

    async def call(method: str, url: str, **kw):
        for _ in range(8):
            r = await api.request(method, url, **kw)
            if r.status_code == 429:
                await asyncio.sleep(float(r.json().get("retry_after", 2)) + 0.25)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"rate limited on {url}")

    edited = recorded = 0
    async with api:
        me = (await call("GET", "/users/@me"))["id"]
        for ch in channels:
            before = None
            while True:
                page = await call("GET", f"/channels/{ch}/messages",
                                  params={"limit": 100, **({"before": before} if before else {})})
                if not page:
                    break
                for m in page:
                    ids = [c.get("custom_id", "") for row in m.get("components") or [] for c in row.get("components") or []]
                    cid = next((int(i.split(":")[1]) for i in ids if i.startswith(discord.RESUME_BUTTON_PREFIX)), None)
                    if m["author"]["id"] != me or cid is None:
                        continue
                    f = s.jobs_dir / f"{cid}.json"
                    rec = _json.loads(f.read_text()) if f.exists() else {}
                    rec.update(message_id=m["id"], discord_channel_id=ch, route=rec.get("route") or routes.get(ch),
                               sent_at=rec.get("sent_at") or m["timestamp"][:19] + "+00:00")
                    if f.exists():
                        f.write_text(discord.dumps(rec))
                        recorded += 1
                    if not any(i.startswith(discord.STATUS_BUTTON_PREFIX) for i in ids):
                        url = next((c.get("url") for row in m["components"] for c in row["components"] if c.get("url")),
                                   rec.get("apply_url"))
                        await call("PATCH", f"/channels/{ch}/messages/{m['id']}",
                                   json={"components": discord.buttons(cid, url)})
                        edited += 1
                        await asyncio.sleep(0.3)
                before = page[-1]["id"]
                if datetime.fromisoformat(page[-1]["timestamp"]) < cutoff:
                    break
    print(f"updated buttons on {edited} alerts; recorded message ids for {recorded}")


def _write_env(path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values:
            lines[i] = f"{key}={values[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in done]
    path.write_text("\n".join(lines) + "\n")


async def cmd_resume(args) -> None:
    from . import resume
    s = config.load()
    job = resume.load_job(s, args.job_id)
    if not job:
        raise SystemExit(f"job #{args.job_id} not found")
    print(f"Creating resume for {job['company']} · {job['title']} (a few minutes)…")
    res = await resume.generate(s, job)
    print(("✅ " + str(res.pdf)) if res.ok else "❌ failed", f"\nfolder: {res.folder}\n{res.summary}")


def cmd_explain(args) -> None:
    s = config.load()
    job = NormalizedJob(source="manual:x", source_job_id="0", company=args.company, title=args.title,
                        url="https://example.com", locations=args.location or [], terms=args.term or [],
                        level_hint=args.level_hint, description=args.description)
    print(classify(job, s.relevance))


def cmd_recent(args) -> None:
    s = config.load()
    db = Store(s.db_path)
    rows = db.all("SELECT c.id, c.company, c.title, c.level, c.category, c.citizenship, a.status, c.apply_url"
                  " FROM canonical_jobs c LEFT JOIN alerts a ON a.canonical_job_id=c.id AND a.alert_type='new'"
                  " WHERE c.relevant=1 AND c.reason NOT LIKE 'seeded%' ORDER BY c.id DESC LIMIT ?", args.n)
    for r in rows:
        print(f"#{r['id']:<6} [{r['status'] or '-':^9}] {r['level']:<8} {r['category']:<8} {r['company'][:22]:<22} "
              f"{r['title'][:70]}  ({r['citizenship'] or 'unknown'})\n        {r['apply_url']}")


def cmd_stats(args) -> None:
    s = config.load()
    db = Store(s.db_path)
    print("canonical jobs:", db.one("SELECT COUNT(*) FROM canonical_jobs")[0],
          "| relevant:", db.one("SELECT COUNT(*) FROM canonical_jobs WHERE relevant=1")[0],
          "| of which seeded silently:", db.one("SELECT COUNT(*) FROM canonical_jobs WHERE reason LIKE 'seeded%'")[0])
    print("alerts:", dict(db.all("SELECT status, COUNT(*) FROM alerts GROUP BY 1")))
    print("top reject reasons:")
    for r in db.all("SELECT reason, COUNT(*) n FROM canonical_jobs WHERE relevant=0 GROUP BY 1 ORDER BY 2 DESC LIMIT 12"):
        print(f"   {r['n']:>7}  {r['reason']}")
    bad = db.all("SELECT key, consecutive_failures, last_error FROM sources WHERE consecutive_failures>0")
    print(f"sources: {db.one('SELECT COUNT(*) FROM sources')[0]} known, {len(bad)} failing")
    for b in bad:
        print(f"   {b['key']}: ×{b['consecutive_failures']} {b['last_error']}")


def main() -> None:
    p = argparse.ArgumentParser(prog="jobalerts")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    o = sub.add_parser("once")
    o.add_argument("--source", help="substring of a source key, e.g. greenhouse:anthropic or simplify")
    o.add_argument("--no-send", action="store_true", help="collect only; leave alerts pending")
    sub.add_parser("test-discord")
    ua = sub.add_parser("upgrade-alerts")
    ua.add_argument("--days", type=int, default=14, help="how far back to look in each channel")
    sc = sub.add_parser("setup-channels")
    sc.add_argument("--category", default="Job Alerts", help="category the channels go in")
    e = sub.add_parser("explain")
    e.add_argument("title")
    e.add_argument("-c", "--company", default="Example")
    e.add_argument("-l", "--location", action="append")
    e.add_argument("-t", "--term", action="append")
    e.add_argument("--level-hint", choices=["intern", "new_grad"])
    e.add_argument("-d", "--description")
    r = sub.add_parser("recent")
    r.add_argument("-n", type=int, default=20)
    sub.add_parser("stats")
    sub.add_parser("bot")
    rs = sub.add_parser("resume")
    rs.add_argument("job_id", type=int)
    sub.add_parser("usage", help="Claude tokens used by resume / cover letter / answer runs")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    {"run": lambda: asyncio.run(cmd_run(args)), "once": lambda: asyncio.run(cmd_once(args)),
     "test-discord": lambda: asyncio.run(cmd_test_discord(args)), "explain": lambda: cmd_explain(args),
     "setup-channels": lambda: asyncio.run(cmd_setup_channels(args)),
     "upgrade-alerts": lambda: asyncio.run(cmd_upgrade_alerts(args)),
     "recent": lambda: cmd_recent(args), "stats": lambda: cmd_stats(args),
     "bot": lambda: _bot_run(), "resume": lambda: asyncio.run(cmd_resume(args)),
     "usage": lambda: cmd_usage(args)}[args.cmd]()


def cmd_usage(_args) -> None:
    from . import usage
    from .config import load
    from .resume import output_root
    usage.backfill(output_root(load()))
    print(usage.summary())


def _bot_run() -> None:
    from . import bot   # discord.py is only installed on the host, not in the Docker image
    bot.run()


if __name__ == "__main__":
    main()
