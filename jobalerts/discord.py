"""Discord webhook delivery: drains the alerts outbox (research §13.1)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from .config import Settings
from .db import Store, dumps, now

log = logging.getLogger(__name__)

COLORS = {"ai_ml": 0x8B5CF6, "research": 0x0EA5E9, "software": 0x22C55E, "data": 0xF59E0B, "quant": 0xEF4444}
CATEGORY_LABEL = {"ai_ml": "AI / ML", "research": "Research", "software": "Software", "data": "Data", "quant": "Quant"}
LEVEL_LABEL = {"intern": "🎓 Internship", "new_grad": "🚀 New grad / entry", "entry": "Entry / unlevelled"}
SOURCE_LABEL = {"greenhouse": "Greenhouse", "ashby": "Ashby", "lever": "Lever", "workday": "Workday",
                "amazon": "amazon.jobs", "eightfold": "Eightfold", "rippling": "Rippling", "simplify": "Simplify list",
                "simplify:vansh-internships": "vanshb03 list", "simplify:vansh-new-grad": "vanshb03 list",
                "markdown": "speedyapply list", "dover": "Dover job board", "getro": "VC board", "consider": "VC board"}
TIER_LABEL = {"big_tech": "Big Tech", "tier1": "Tier 1", "tier2": "Tier 2", "tier3": "Tier 3"}
# Discord channels for route_by: tier, in priority order: route → (channel name, topic).
TIER_CHANNELS = {
    "big_tech": ("big-tech", "Big Tech openings: Meta, Google, Apple, Amazon, Microsoft, NVIDIA, TikTok, …"),
    "tier1": ("tier-1", "Tier 1: top AI labs, quant firms and the strongest startups (OpenAI, Anthropic, Jane Street, …)"),
    "tier2": ("tier-2", "Tier 2: strong tech companies and well-funded startups"),
    "tier3": ("tier-3", "Tier 3: other tracked companies"),
    "other": ("other-companies", "Everything else: companies not in companies.yaml, from GitHub lists and VC boards"),
    "ops": ("job-alerts-status", "Daily summary and broken-source warnings"),
}
MAX_ATTEMPTS = 5
SEND_GAP = 1.1           # webhook limit is 5 requests / 2 s; stay well under it
API = "https://discord.com/api/v10"
RESUME_BUTTON_PREFIX = "resume:"
COVER_BUTTON_PREFIX = "cover:"
STATUS_BUTTON_PREFIX = "status:"          # status:applied:<job id>, status:later:…, status:skip:…


def render_job(db: Store, cid: int, mention_role: str | None) -> dict:
    j = db.one("SELECT * FROM canonical_jobs WHERE id=?", cid)
    srcs = db.all("SELECT source, first_seen_at FROM job_sources WHERE canonical_job_id=? ORDER BY first_seen_at", cid)
    locs = json.loads(j["locations"] or "[]")
    terms = [t for t in json.loads(j["terms"] or "[]") if t != "N/A"]
    flags = json.loads(j["flags"] or "[]")

    fields = [
        {"name": "📍 Location", "value": _clip(", ".join(locs) or "—", 200), "inline": True},
        {"name": "Level", "value": LEVEL_LABEL.get(j["level"], j["level"] or "—"), "inline": True},
        {"name": "Area", "value": CATEGORY_LABEL.get(j["category"], j["category"] or "—"), "inline": True},
    ]
    if terms:
        fields.append({"name": "Term", "value": ", ".join(terms), "inline": True})
    if j["posted_at"]:
        ts = int(datetime.fromisoformat(j["posted_at"]).timestamp())
        fields.append({"name": "Posted", "value": f"<t:{ts}:R>", "inline": True})
    if j["compensation"]:
        fields.append({"name": "💰 Pay", "value": _clip(j["compensation"], 100), "inline": True})

    cz = {"ok": "✅ No citizenship requirement found", "warn": "⚠ Export-control / US-person wording — check",
          "reject": "⛔ Requires citizenship", None: "❔ Not verified (no description)",
          "unknown": "❔ Not verified (no description)"}[j["citizenship"]]
    if j["no_sponsorship"]:
        cz += "\n🛂 Says no visa sponsorship"
    if j["citizenship"] == "warn" and j["citizenship_evidence"]:
        cz += f"\n> {_clip(j['citizenship_evidence'], 180)}"
    fields.append({"name": "Eligibility", "value": cz, "inline": False})

    src_names = sorted({_source_label(s["source"]) for s in srcs})
    fields.append({"name": "Seen on", "value": ", ".join(src_names), "inline": False})
    if flags:
        fields.append({"name": "Heads-up", "value": "\n".join(f"• {f}" for f in flags), "inline": False})

    company = j["company"] + (f"  ·  {TIER_LABEL.get(j['tier'], j['tier'])}" if j["tier"] else "")
    embed = {
        "title": _clip(j["title"], 250),
        "url": j["apply_url"],
        "author": {"name": _clip(company, 250)},
        "color": COLORS.get(j["category"], 0x64748B),
        "fields": fields,
        "footer": {"text": f"job #{j['id']}" + (f" · {j['ats']} {j['ats_id']}" if j["ats_id"] else "")},
        "timestamp": j["first_seen_at"],
    }
    if j["description_snippet"]:
        embed["description"] = _clip(j["description_snippet"], 350)
    msg: dict = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if mention_role:
        msg["content"] = f"<@&{mention_role}>"
        msg["allowed_mentions"] = {"roles": [str(mention_role)]}
    return msg


def buttons(cid: int, apply_url: str | None) -> list[dict]:
    """Two action rows for bot-sent alerts, handled by `python -m jobalerts bot`:
    ✅ Applied · ⭐ Later · ⏭ Skip · Apply (link)   /   📄 Create resume · ✉️ Cover letter"""
    def btn(label: str, emoji: str, custom_id: str, style: int = 2) -> dict:
        return {"type": 2, "style": style, "label": label, "emoji": {"name": emoji}, "custom_id": custom_id}
    row1 = [btn("Applied", "✅", f"{STATUS_BUTTON_PREFIX}applied:{cid}", 3),
            btn("Later", "⭐", f"{STATUS_BUTTON_PREFIX}later:{cid}"),
            btn("Skip", "⏭", f"{STATUS_BUTTON_PREFIX}skip:{cid}")]
    if apply_url and len(apply_url) <= 512:
        row1.append({"type": 2, "style": 5, "label": "Apply", "url": apply_url})
    row2 = [btn("Create resume", "📄", f"{RESUME_BUTTON_PREFIX}{cid}", 1),
            btn("Cover letter", "✉️", f"{COVER_BUTTON_PREFIX}{cid}", 1)]
    return [{"type": 1, "components": row1}, {"type": 1, "components": row2}]


def job_buttons(db: Store, cid: int) -> list[dict]:
    j = db.one("SELECT apply_url FROM canonical_jobs WHERE id=?", cid)
    return buttons(cid, j["apply_url"] if j else None)


def job_record(db: Store, cid: int) -> dict | None:
    j = db.one("SELECT * FROM canonical_jobs WHERE id=?", cid)
    if not j:
        return None
    a = db.one("SELECT channel, sent_at, message_id, discord_channel_id FROM alerts"
               " WHERE canonical_job_id=? AND alert_type='new' ORDER BY id DESC LIMIT 1", cid)
    return {
        "id": j["id"], "company": j["company"], "title": j["title"], "apply_url": j["apply_url"],
        "tier": j["tier"], "route": a["channel"] if a else None, "sent_at": a["sent_at"] if a else None,
        "message_id": a["message_id"] if a else None, "discord_channel_id": a["discord_channel_id"] if a else None,
        "color": COLORS.get(j["category"], 0x64748B),
        "locations": json.loads(j["locations"] or "[]"), "level": j["level"], "category": j["category"],
        "terms": [t for t in json.loads(j["terms"] or "[]") if t != "N/A"], "posted_at": j["posted_at"],
        "compensation": j["compensation"], "citizenship": j["citizenship"],
        "description": j["description"] or j["description_snippet"],
        "description_is_full": bool(j["description"]),
    }


def export_job(settings: Settings, db: Store, cid: int) -> None:
    rec = job_record(db, cid)
    if rec:
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        tmp = settings.jobs_dir / f"{cid}.json.tmp"
        tmp.write_text(dumps(rec))
        tmp.replace(settings.jobs_dir / f"{cid}.json")


def _source_label(key: str) -> str:
    kind, _, slug = key.partition(":")
    if kind in ("getro", "consider"):
        return f"{slug.replace('-', ' ').title() if slug != 'a16z' else 'a16z'} portfolio board"
    return SOURCE_LABEL.get(key) or SOURCE_LABEL.get(kind, key)


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


async def post(client: httpx.AsyncClient, url: str, payload: dict, bot_token: str | None = None) -> dict:
    """Webhook post, or with bot_token, `url` is a channel id and the message is sent as the bot. Returns the
    created message (its id and channel_id)."""
    for _ in range(4):
        if bot_token:
            r = await client.post(f"{API}/channels/{url}/messages", json=payload,
                                  headers={"Authorization": f"Bot {bot_token}"})
        else:
            r = await client.post(url, params={"wait": "true"}, json=payload)
        if r.status_code == 429:
            wait = float(r.json().get("retry_after", 2)) + 0.25
            log.info("Discord rate limit, waiting %.1fs", wait)
            await asyncio.sleep(wait)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Discord HTTP {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError:
            return {}
    raise RuntimeError("Discord rate limit: gave up after 4 tries")


async def drain(settings: Settings, db: Store, limit: int | None = None) -> int:
    limit = limit or int(settings.alerts.get("max_per_cycle", 40))
    rows = db.all("SELECT * FROM alerts WHERE status='pending' ORDER BY (alert_type='ops') DESC, id LIMIT ?", limit)
    if not rows:
        return 0
    sent = 0
    mention = settings.alerts.get("mention_role_id")
    async with httpx.AsyncClient(timeout=20) as client:
        for a in rows:
            target = settings.target_for(a["channel"])
            if not target:
                log.warning("no Discord destination configured (set DISCORD_WEBHOOK_URL in .env); %d alerts waiting",
                            len(rows))
                return sent
            mode, dest = target
            try:
                if a["payload"]:
                    payload = json.loads(a["payload"])
                else:
                    payload = render_job(db, a["canonical_job_id"], mention)
                    if mode == "bot":
                        payload["components"] = job_buttons(db, a["canonical_job_id"])
                msg = await post(client, dest, payload, settings.bot_token if mode == "bot" else None)
                db.exec("UPDATE alerts SET status='sent', sent_at=?, attempts=attempts+1, message_id=?,"
                        " discord_channel_id=? WHERE id=?", now(), msg.get("id"), msg.get("channel_id"), a["id"])
                if a["canonical_job_id"]:
                    export_job(settings, db, a["canonical_job_id"])      # after sending: carries the message id
                sent += 1
            except Exception as e:  # noqa: BLE001
                status = "failed" if a["attempts"] + 1 >= MAX_ATTEMPTS else "pending"
                db.exec("UPDATE alerts SET attempts=attempts+1, status=?, last_error=? WHERE id=?",
                        status, str(e)[:500], a["id"])
                log.warning("alert %s failed: %s", a["id"], e)
            await asyncio.sleep(SEND_GAP)
    return sent


def queue_daily_summary(settings: Settings, db: Store) -> None:
    hour = settings.alerts.get("daily_summary_utc_hour")
    t = datetime.now(timezone.utc)
    if hour is None or t.hour < int(hour):
        return
    day = t.date().isoformat()
    since = (t - timedelta(days=1)).isoformat(timespec="seconds")
    new = db.one("SELECT COUNT(*) FROM alerts WHERE alert_type='new' AND status='sent' AND sent_at>=?", since)[0]
    by_cat = db.all("SELECT c.category, COUNT(*) n FROM alerts a JOIN canonical_jobs c ON c.id=a.canonical_job_id"
                    " WHERE a.alert_type='new' AND a.status='sent' AND a.sent_at>=? GROUP BY 1 ORDER BY 2 DESC", since)
    blocked = db.one("SELECT COUNT(*) FROM canonical_jobs WHERE reason LIKE 'requires US citizenship%' AND first_seen_at>=?",
                     since)[0]
    from .tracker import Tracker, path_for
    marks = Tracker(path_for(settings.jobs_dir)).all().values()
    applied = sum(1 for e in marks if e["status"] == "applied" and e["at"] >= since)
    srcs = db.all("SELECT key, consecutive_failures, last_error FROM sources WHERE consecutive_failures>0 ORDER BY 2 DESC")
    total_src = db.one("SELECT COUNT(*) FROM sources")[0]
    by_channel = db.all("SELECT a.channel, COUNT(*) n FROM alerts a WHERE a.alert_type='new' AND a.status='sent'"
                        " AND a.sent_at>=? GROUP BY 1", since)
    order = {r: i for i, r in enumerate(TIER_CHANNELS)}
    by_channel = sorted(by_channel, key=lambda r: order.get(r["channel"], 99))
    lines = [f"📊 **Daily summary — {day}**",
             f"New relevant jobs sent (24h): **{new}**" +
             (" (" + ", ".join(f"{CATEGORY_LABEL.get(r['category'], r['category'])} {r['n']}" for r in by_cat) + ")" if by_cat else ""),
             *([" · ".join(f"#{TIER_CHANNELS.get(r['channel'], (r['channel'],))[0]} {r['n']}" for r in by_channel)]
               if by_channel else []),
             f"You applied to: **{applied}** (24h)",
             f"Filtered out for citizenship/clearance: {blocked}",
             f"Sources healthy: {total_src - len(srcs)}/{total_src}"]
    for s in srcs[:10]:
        lines.append(f"• `{s['key']}` failing ×{s['consecutive_failures']}: {_clip(s['last_error'] or '', 120)}")
    db.exec("INSERT INTO alerts(alert_type, channel, idempotency_key, payload, created_at) VALUES ('summary','ops',?,?,?)"
            " ON CONFLICT(idempotency_key) DO NOTHING", f"summary:{day}", dumps({"content": "\n".join(lines)}), now())
