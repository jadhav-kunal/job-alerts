"""Local API for the browser extension (extension/), served by the bot process on 127.0.0.1 only.

  GET  /api/ping                     is the helper running?
  GET  /api/match?url=<page url>     which alert this application page belongs to, its status, resume, cover letter
  GET  /api/profile                  config/profile.yaml (the answers the extension fills in)
  GET  /api/file/resume/<job id>     tailored resume for the job, or profile.default_resume
  GET  /api/file/cover/<job id>      the job's cover letter PDF
  POST /api/status   {job_id, status}  applied / later / skip / none; also recolours the Discord alert
  POST /api/generate {job_id, kind}    start a resume or cover letter (the same queue as the Discord buttons)
  POST /api/answers  {job_id, url, questions}  Claude drafts answers for the questions Fill left empty → {run_id}
  GET  /api/answers/<run_id>         {status: running | done | error, answers, notes}
  POST /api/log      {lines}           what the extension is doing, appended to data/extension.log

Every request needs the X-Job-Alerts-Token header (data/helper_token, pasted once into the extension's options).
No CORS headers are sent, so web pages cannot read anything; the custom header makes them unable to POST either.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from . import answers, cover_letter
from .config import ROOT
from .normalize import ats_identity, normalize_url

if TYPE_CHECKING:
    from .bot import JobBot

log = logging.getLogger(__name__)
TOKEN_FILE = ROOT / "data/helper_token"
EXT_LOG = ROOT / "data/extension.log"


def token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    t = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(t + "\n")
    os.chmod(TOKEN_FILE, 0o600)
    return t


def match(jobs: list[dict], url: str) -> dict | None:
    """The alert whose apply URL is this page: same normalized URL, else same ATS job id (an application page is
    often /apply or /application under the posting, or the company's own domain with ?gh_jid=)."""
    norm, ident = normalize_url(url), ats_identity(url)
    by_ats = None
    for j in jobs:
        if not j.get("apply_url"):
            continue
        if normalize_url(j["apply_url"]) == norm:
            return j
        if ident and by_ats is None:
            other = ats_identity(j["apply_url"])
            if other and other[0] == ident[0] and other[2] == ident[2]:
                by_ats = j
    return by_ats


def _default_resume() -> Path | None:
    p = (cover_letter.profile() or {}).get("default_resume")
    path = Path(os.path.expanduser(p)) if p else None
    return path if path and path.exists() else None


def build_app(bot: "JobBot") -> web.Application:
    secret = token()

    @web.middleware
    async def auth(request: web.Request, handler):
        if request.headers.get("X-Job-Alerts-Token") != secret:
            return web.json_response({"error": "bad or missing token"}, status=401)
        return await handler(request)

    def describe(j: dict) -> dict:
        tailored = bot.existing("resume", j)
        cover = bot.existing("cover", j)
        cover_txt = cover.parent / "cover_letter.txt" if cover else None
        return {
            "job": {k: j.get(k) for k in ("id", "company", "title", "apply_url", "route", "level")},
            "status": (bot.tracker.get(int(j["id"])) or {}).get("status"),
            "resume": {"available": bool(tailored or _default_resume()), "tailored": bool(tailored),
                       "name": (tailored or _default_resume() or Path("")).name,
                       "generating": ("resume", int(j["id"])) in bot.in_progress},
            "cover_letter": {"available": bool(cover), "name": cover.name if cover else None,
                             "text": cover_txt.read_text() if cover_txt and cover_txt.exists() else None,
                             "generating": ("cover", int(j["id"])) in bot.in_progress},
        }

    async def ping(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def match_route(request: web.Request) -> web.Response:
        jobs = bot.jobs.all()
        # The page URL, then the referrer: a Greenhouse form embedded on a company site runs in an iframe whose own
        # URL is /embed/job_app?for=…&token=… while the referrer is the company's job page.
        j = next((hit for u in request.query.getall("url", []) if (hit := match(jobs, u))), None)
        if not j:
            default = _default_resume()
            return web.json_response({"found": False, "resume": {"available": bool(default), "tailored": False,
                                                                 "name": default.name if default else None}})
        return web.json_response({"found": True, **describe(j)})

    async def profile_route(_: web.Request) -> web.Response:
        return web.json_response(cover_letter.profile())

    async def file_route(request: web.Request) -> web.Response:
        kind, raw_id = request.match_info["kind"], request.match_info["job_id"]
        j = bot.jobs.get(int(raw_id)) if raw_id.isdigit() else None
        if kind == "resume":
            path = (bot.existing("resume", j) if j else None) or _default_resume()
        elif kind == "cover" and j:
            path = bot.existing("cover", j)
        else:
            path = None
        if not path:
            return web.json_response({"error": "no file"}, status=404)
        return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{path.name}"',
                                               "X-File-Name": path.name})

    async def status_route(request: web.Request) -> web.Response:
        body = await request.json()
        job_id, status = int(body["job_id"]), str(body["status"])
        if status not in ("applied", "later", "skip", "none"):
            return web.json_response({"error": "bad status"}, status=400)
        await bot.set_status_from_helper(job_id, status)
        return web.json_response({"ok": True, "status": status})

    async def generate_route(request: web.Request) -> web.Response:
        body = await request.json()
        kind = "cover" if body.get("kind") == "cover" else "resume"
        j = bot.jobs.get(int(body["job_id"]))
        if not j:
            return web.json_response({"error": "unknown job"}, status=404)
        if (kind, int(j["id"])) not in bot.in_progress:
            asyncio.create_task(bot.generate(kind, j))
        return web.json_response({"started": True})

    runs: dict[str, dict] = {}

    async def answers_route(request: web.Request) -> web.Response:
        body = await request.json()
        questions = [q for q in body.get("questions") or [] if isinstance(q, dict) and q.get("key")][:80]
        if not questions:
            return web.json_response({"error": "no questions"}, status=400)
        raw = body.get("job_id")
        job = bot.jobs.get(int(raw)) if str(raw or "").isdigit() else None
        run_id = secrets.token_hex(6)
        runs[run_id] = {"status": "running"}
        for old in list(runs)[:-50]:              # keep the latest runs only
            runs.pop(old, None)

        async def go():
            try:
                runs[run_id] = await answers.generate(bot.settings, job, questions, run_id, body.get("url") or "",
                                                      body.get("referrer") or "", body.get("page_title") or "")
            except Exception as e:                # report it to the panel instead of leaving it "running"
                log.exception("answers run %s failed", run_id)
                runs[run_id] = {"status": "error", "error": str(e)[:300]}
        asyncio.create_task(go())
        return web.json_response({"run_id": run_id})

    async def answers_status(request: web.Request) -> web.Response:
        r = runs.get(request.match_info["run_id"])
        return web.json_response(r or {"status": "error", "error": "unknown run (was the bot restarted?)"})

    async def log_route(request: web.Request) -> web.Response:
        lines = [str(x).replace("\n", " ")[:500] for x in (await request.json()).get("lines") or []][:200]
        if lines:
            if EXT_LOG.exists() and EXT_LOG.stat().st_size > 5_000_000:      # keep it small: one old copy
                EXT_LOG.replace(EXT_LOG.with_suffix(".log.1"))
            with EXT_LOG.open("a") as f:
                f.write("".join(line + "\n" for line in lines))
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[auth])
    app.add_routes([web.get("/api/ping", ping), web.get("/api/match", match_route),
                    web.get("/api/profile", profile_route), web.get("/api/file/{kind}/{job_id}", file_route),
                    web.post("/api/status", status_route), web.post("/api/generate", generate_route),
                    web.post("/api/answers", answers_route), web.get("/api/answers/{run_id}", answers_status),
                    web.post("/api/log", log_route)])
    return app


async def start(bot: "JobBot") -> None:
    port = int((bot.settings.raw.get("helper") or {}).get("port", 8765))
    runner = web.AppRunner(build_app(bot), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", port).start()
        log.info("browser-extension helper on http://127.0.0.1:%d (token in %s)", port, TOKEN_FILE)
    except OSError as e:
        log.warning("browser-extension helper not started on port %d: %s", port, e)
