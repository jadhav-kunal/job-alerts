"""Discord bot for the alert buttons and slash commands. Runs on the host next to the Docker daemon:
`python -m jobalerts bot` (or at login via deploy/com.jobalerts.resumebot.plist).

  ✅ Applied / ⭐ Later / ⏭ Skip   record the job's status (tracker.py) and recolour the alert; a second click undoes
  📄 Create resume / ✉️ Cover letter   Claude Code writes a tailored PDF and posts it back
  /todo [channel]                 alerts you have not acted on yet, oldest first
  /resume <id>, /cover <id>       the same as the buttons, for alerts that have none

It also serves the browser extension's local API (helper.py) on 127.0.0.1. Only gateway interactions are used, so no
public URL or port is needed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands

from . import config, cover_letter, resume
from .discord import (COLORS, COVER_BUTTON_PREFIX, RESUME_BUTTON_PREFIX, STATUS_BUTTON_PREFIX, TIER_CHANNELS)
from .tracker import STATUSES, Tracker, path_for

log = logging.getLogger(__name__)

STATUS_COLORS = {"applied": 0x4B5563, "later": 0xFACC15, "skip": 0x1F2937}
STATUS_EMOJI = {"applied": "✅", "later": "⭐", "skip": "⏭"}
_TITLE_MARK = re.compile(r"^(?:✅|⭐|⏭)\s+")
_FOOTER_MARK = re.compile(r"\s+·\s+(?:✅|⭐|⏭) .*$")
CHANNEL_CHOICES = [app_commands.Choice(name=f"#{name}", value=route)
                   for route, (name, _) in TIER_CHANNELS.items() if route != "ops"]


def decorate(embed: dict, status: str | None, color: int | None, when: datetime | None = None) -> dict:
    """The alert embed with the status shown (title mark, colour, footer), or restored when status is None."""
    e = json.loads(json.dumps(embed))
    title = _TITLE_MARK.sub("", e.get("title") or "")
    footer = _FOOTER_MARK.sub("", (e.get("footer") or {}).get("text") or "")
    if status in STATUSES:
        when = when or datetime.now()
        e["title"] = f"{STATUS_EMOJI[status]} {title}"[:256]
        e["color"] = STATUS_COLORS[status]
        footer = f"{footer} · {STATUSES[status]} {when.strftime('%b')} {when.day}"
    else:
        e["title"] = title
        if color is not None:
            e["color"] = color
    if footer:
        e["footer"] = {**(e.get("footer") or {}), "text": footer}
    return e


class Jobs:
    """The per-alert JSON files the daemon writes to data/jobs/ when it sends an alert (read-only here)."""

    def __init__(self, settings: config.Settings):
        self.dir = settings.jobs_dir
        self.settings = settings
        self._cache: dict[Path, tuple[float, dict]] = {}

    def all(self) -> list[dict]:
        out = []
        for f in self.dir.glob("*.json"):
            try:
                mtime = f.stat().st_mtime
                if (hit := self._cache.get(f)) and hit[0] == mtime:
                    out.append(hit[1])
                    continue
                rec = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            rec.setdefault("sent_at", datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds"))
            self._cache[f] = (mtime, rec)
            out.append(rec)
        return out

    def get(self, job_id: int) -> dict | None:
        return resume.load_job(self.settings, job_id)


def todo_lines(jobs: list[dict], statuses: dict[int, dict], route: str | None, days: int, include_later: bool,
               guild_id: int | None) -> tuple[list[str], dict[str, int]]:
    """(lines for the list, untouched count per route) for /todo."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    picked, counts = [], {}
    for j in jobs:
        if (j.get("sent_at") or "") < since:
            continue
        st = (statuses.get(int(j["id"])) or {}).get("status")
        if st in ("applied", "skip") or (st == "later" and not include_later):
            continue
        r = j.get("route") or "unknown"
        counts[r] = counts.get(r, 0) + 1
        if route is None or r == route:
            picked.append((j, st))
    picked.sort(key=lambda x: x[0].get("sent_at") or "")
    lines = []
    for j, st in picked:
        if j.get("message_id") and j.get("discord_channel_id") and guild_id:
            link = f"https://discord.com/channels/{guild_id}/{j['discord_channel_id']}/{j['message_id']}"
        else:
            link = j.get("apply_url")
        age = _age(j.get("sent_at"))
        mark = "⭐ " if st == "later" else ""
        label = f"{j['company']} · {j['title']}".replace("[", "(").replace("]", ")")
        lines.append(f"{mark}[{label[:90]}]({link}) · {age} · `#{j['id']}`")
    return lines, counts


def _age(iso: str | None) -> str:
    try:
        d = datetime.now(timezone.utc) - datetime.fromisoformat(iso)   # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "?"
    return f"{int(d.total_seconds() // 3600)}h" if d < timedelta(days=1) else f"{d.days}d"


class JobBot(discord.Client):
    def __init__(self, settings: config.Settings):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.sem = asyncio.Semaphore(int(settings.resume.get("concurrency", 1)))
        self.in_progress: set[tuple[str, int]] = set()
        self.queued = 0
        self.tracker = Tracker(path_for(settings.jobs_dir))
        self.jobs = Jobs(settings)

        @self.tree.command(name="resume", description="Create a tailored resume for a job (id is in the alert footer)")
        @app_commands.describe(job_id="the number after 'job #' in the alert footer",
                               regenerate="make a new one even if a PDF already exists")
        async def resume_cmd(interaction: discord.Interaction, job_id: int, regenerate: bool = False) -> None:
            await self.handle_document(interaction, "resume", job_id, regenerate)

        @self.tree.command(name="cover", description="Write a cover letter for a job (id is in the alert footer)")
        @app_commands.describe(job_id="the number after 'job #' in the alert footer",
                               regenerate="write a new one even if one already exists")
        async def cover_cmd(interaction: discord.Interaction, job_id: int, regenerate: bool = False) -> None:
            await self.handle_document(interaction, "cover", job_id, regenerate)

        @self.tree.command(name="todo", description="Alerts you have not applied to or skipped yet, oldest first")
        @app_commands.describe(channel="one channel (default: all)", days="look back this many days (default 14)",
                               include_later="also list the ones saved with ⭐ Later (default yes)")
        @app_commands.choices(channel=CHANNEL_CHOICES)
        async def todo_cmd(interaction: discord.Interaction, channel: app_commands.Choice[str] | None = None,
                           days: app_commands.Range[int, 1, 90] = 14, include_later: bool = True) -> None:
            await self.handle_todo(interaction, channel.value if channel else None, days, include_later)

    async def setup_hook(self) -> None:
        self.tree.on_error = self._tree_error  # type: ignore[assignment]
        from . import helper
        await helper.start(self)

    async def on_ready(self) -> None:
        for guild in self.guilds:
            await self._sync(guild)
        log.info("bot ready as %s in %d server(s)", self.user, len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._sync(guild)

    async def _sync(self, guild: discord.Guild) -> None:
        # Guild-scoped sync shows the commands immediately (global sync can take up to an hour).
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def _tree_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception("command failed", exc_info=error)

    # ── buttons ──────────────────────────────────────────────────────────
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.component:
            return
        cid = str((interaction.data or {}).get("custom_id", ""))
        try:
            if cid.startswith(STATUS_BUTTON_PREFIX):
                status, job_id = cid.removeprefix(STATUS_BUTTON_PREFIX).split(":")
                await self.handle_status(interaction, status, int(job_id))
            elif cid.startswith(RESUME_BUTTON_PREFIX):
                await self.handle_document(interaction, "resume", int(cid.removeprefix(RESUME_BUTTON_PREFIX)), False)
            elif cid.startswith(COVER_BUTTON_PREFIX):
                await self.handle_document(interaction, "cover", int(cid.removeprefix(COVER_BUTTON_PREFIX)), False)
        except ValueError:
            return

    async def handle_status(self, interaction: discord.Interaction, status: str, job_id: int) -> None:
        current = (self.tracker.get(job_id) or {}).get("status")
        new = "none" if current == status else status        # a second click on the same button undoes it
        self.tracker.set(job_id, new, via="discord")
        msg = interaction.message
        if msg and msg.embeds:
            embed = decorate(msg.embeds[0].to_dict(), new if new != "none" else None, self._color(job_id))
            await interaction.response.edit_message(embed=discord.Embed.from_dict(embed))
        else:
            await interaction.response.send_message(f"{STATUSES.get(new, 'Cleared')}: job #{job_id}", ephemeral=True)

    def _color(self, job_id: int) -> int | None:
        j = self.jobs.get(job_id) or {}
        return j.get("color") or COLORS.get(j.get("category") or "", 0x64748B)

    async def set_status_from_helper(self, job_id: int, status: str) -> None:
        """Status set from the browser extension: record it and recolour the Discord alert too."""
        self.tracker.set(job_id, status, via="extension")
        j = self.jobs.get(job_id) or {}
        if not (j.get("message_id") and j.get("discord_channel_id")):
            return
        try:
            msg = await self.get_partial_messageable(int(j["discord_channel_id"])).fetch_message(int(j["message_id"]))
            if msg.embeds:
                embed = decorate(msg.embeds[0].to_dict(), status if status != "none" else None, self._color(job_id))
                await msg.edit(embed=discord.Embed.from_dict(embed))
        except discord.HTTPException as e:
            log.info("could not update alert for job #%s: %s", job_id, e)

    # ── /todo ────────────────────────────────────────────────────────────
    async def handle_todo(self, interaction: discord.Interaction, route: str | None, days: int,
                          include_later: bool) -> None:
        lines, counts = todo_lines(self.jobs.all(), self.tracker.all(), route, days, include_later,
                                   interaction.guild_id)
        order = [r for r in TIER_CHANNELS if r != "ops"]
        summary = " · ".join(f"#{TIER_CHANNELS[r][0]} **{counts[r]}**" for r in order if counts.get(r))
        head = (f"**{len(lines)} to do in #{TIER_CHANNELS[route][0]}**" if route else
                f"**{sum(counts.values())} to do** (last {days} days)\n{summary or 'nothing left 🎉'}")
        body, shown = [], 0
        budget = 3900 - len(head)
        for i, line in enumerate(lines, 1):
            row = f"{i}. {line}"
            if budget - len(row) - 40 < 0:
                break
            body.append(row)
            budget -= len(row) + 1
            shown += 1
        if shown < len(lines):
            body.append(f"…and {len(lines) - shown} more. Pick one channel to see them.")
        embed = discord.Embed(description=head + ("\n\n" + "\n".join(body) if body else ""), color=0x6366F1)
        embed.set_footer(text="✅ / ⏭ on an alert removes it from this list · ⭐ keeps it here")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── resume / cover letter ────────────────────────────────────────────
    async def handle_document(self, interaction: discord.Interaction, kind: str, job_id: int,
                              regenerate: bool) -> None:
        job = self.jobs.get(job_id)
        if not job:
            await interaction.response.send_message(f"Job #{job_id} not found.", ephemeral=True)
            return
        label = f"**{job['company']}** · {job['title']}"
        noun = "resume" if kind == "resume" else "cover letter"
        existing = self.existing(kind, job)
        if existing and not regenerate:
            cmd = "resume" if kind == "resume" else "cover"
            await interaction.response.send_message(
                f"📎 {noun.capitalize()} already made for {label}. `/{cmd} {job_id} regenerate:True` makes a new one.",
                file=discord.File(existing))
            return
        if (kind, job_id) in self.in_progress:
            await interaction.response.send_message(f"⏳ Already writing the {noun} for {label}.", ephemeral=True)
            return
        wait = f" ({self.queued} ahead in the queue)" if self.queued else ""
        await interaction.response.send_message(f"⏳ Writing a {noun} for {label}{wait}. This takes a few minutes.")
        res = await self.generate(kind, job)
        if res.ok and res.pdf:
            text = f"✅ {noun.capitalize()} for {label}\n📁 `{res.folder}`\n{res.summary}"
            await self._reply(interaction, text[:1900], discord.File(res.pdf))
        else:
            await self._reply(interaction, f"❌ {noun.capitalize()} for {label} failed: {res.summary[:1500]}\n"
                                           f"📁 `{res.folder}`")

    def existing(self, kind: str, job: dict) -> Path | None:
        if kind == "cover":
            return cover_letter.existing(self.settings, job)
        f = resume.job_folder(self.settings, job) / resume.pdf_name(self.settings, job)
        return f if f.exists() else None

    async def generate(self, kind: str, job: dict) -> resume.ResumeResult:
        """Queued generation, shared by the buttons, the slash commands and the browser extension."""
        key = (kind, int(job["id"]))
        self.in_progress.add(key)
        self.queued += 1
        try:
            async with self.sem:
                gen = resume.generate if kind == "resume" else cover_letter.generate
                return await gen(self.settings, job)
        except Exception as e:  # noqa: BLE001
            log.exception("%s generation crashed", kind)
            return resume.ResumeResult(False, resume.job_folder(self.settings, job), None, f"crashed: {e}")
        finally:
            self.queued -= 1
            self.in_progress.discard(key)

    async def _reply(self, interaction: discord.Interaction, text: str, file: discord.File | None = None) -> None:
        kwargs = {"file": file} if file else {}
        try:
            await interaction.followup.send(text, **kwargs)   # interaction tokens last 15 min
        except discord.HTTPException:
            if file:
                file.reset()
            await interaction.channel.send(text, **kwargs)     # type: ignore[union-attr]


def run() -> None:
    s = config.load()
    if not s.bot_token:
        raise SystemExit("Set DISCORD_BOT_TOKEN (and DISCORD_CHANNEL_ID) in .env first. See README → Resume button.")
    JobBot(s).run(s.bot_token, log_handler=None)

