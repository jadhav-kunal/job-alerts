"""Tailored resume for one job: Claude Code runs the resume-builder skill headlessly, pdflatex compiles it.

Runs on the host (not in Docker): it needs your `claude` login, your skills in ~/.claude/skills and a TeX install.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import usage
from .config import ROOT, Settings
from .db import Store

log = logging.getLogger(__name__)

# Tools the unattended run may use. Anything else is denied instead of prompting.
ALLOWED_TOOLS = ["Skill", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch",
                 "Bash(pdflatex:*)", "Bash(pdfinfo:*)", "Bash(ls:*)"]
EXTRA_PATH = [str(Path.home() / ".local/bin"), "/Library/TeX/texbin", "/opt/homebrew/bin", "/usr/local/bin"]

PROMPT = """Use the {skill} skill to tailor {name}'s one-page resume to the job in job.md (current directory).

resume.tex in the current directory is already their base resume (a copy of the skill's references/base-resume.tex).
Follow the skill's "Tailor, don't rewrite" section: pick blocks from references/bullet-library.tex and make small
keyword edits with the Edit tool. Do not rewrite resume.tex as a whole, and do not read the other reference files
unless the posting needs a fact the library lacks.

This is an unattended run started from a Discord button, so nobody can answer questions:
- Do not ask for more context. Never invent experience or metrics.
- If job.md says the description is missing or partial, fetch the apply URL with WebFetch to read the full posting.
- Compile with: pdflatex -interaction=nonstopmode -halt-on-error resume.tex
- Check the page count with: pdfinfo resume.pdf . If it is more than one page, tighten the content and recompile.
- Write the skill's change summary to changes.md.
- Finish with a reply of at most 4 short lines: what you emphasised for this role and anything I should double-check.
"""


@dataclass
class ResumeResult:
    ok: bool
    folder: Path
    pdf: Path | None
    summary: str


def _slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:n].strip("_") or "job"


def output_root(settings: Settings) -> Path:
    p = Path(os.path.expanduser(settings.resume.get("output_dir", "resumes")))
    return p if p.is_absolute() else ROOT / p


def job_folder(settings: Settings, job: dict) -> Path:
    return output_root(settings) / f"{_slug(job['company'], 30)}_{_slug(job['title'])}_{job['id']}"


def candidate_name(sep: str = " ") -> str:
    """Your name from config/profile.yaml ("the candidate" when the profile is missing)."""
    try:
        n = (yaml.safe_load((ROOT / "config/profile.yaml").read_text()) or {}).get("name") or {}
    except (OSError, yaml.YAMLError):
        n = {}
    return sep.join(x for x in (n.get("first"), n.get("last")) if x) or ""


def pdf_name(settings: Settings, job: dict) -> str:
    prefix = settings.resume.get("file_prefix") or (f"{candidate_name('_')}_Resume" if candidate_name() else "Resume")
    return f"{prefix}_{_slug(job['company'], 30)}.pdf"


def load_job(settings: Settings, cid: int) -> dict | None:
    """The JSON the daemon exported at send time; falls back to the DB for alerts sent before that existed."""
    f = settings.jobs_dir / f"{cid}.json"
    if f.exists():
        return json.loads(f.read_text())
    from .discord import job_record
    return job_record(Store(settings.db_path), cid)


def job_markdown(job: dict) -> str:
    lines = [f"# {job['title']}", "", f"- Company: {job['company']}", f"- Apply URL: {job['apply_url']}"]
    if job.get("locations"):
        lines.append(f"- Location: {', '.join(job['locations'])}")
    for label, key in (("Level", "level"), ("Area", "category"), ("Pay", "compensation"), ("Posted", "posted_at")):
        if job.get(key):
            lines.append(f"- {label}: {job[key]}")
    if job.get("terms"):
        lines.append(f"- Term: {', '.join(job['terms'])}")
    lines += ["", "## Job description", ""]
    if job.get("description_is_full"):
        lines.append(job["description"])
    elif job.get("description"):
        lines += ["(Partial: only a snippet was stored. Fetch the apply URL for the full posting.)", "",
                  job["description"]]
    else:
        lines.append("(Missing. Fetch the apply URL for the full posting.)")
    return "\n".join(lines) + "\n"


def _pages(pdf: Path) -> int | None:
    import subprocess
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m[1]) if m else None


async def generate(settings: Settings, job: dict) -> ResumeResult:
    cfg = settings.resume
    folder = job_folder(settings, job)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.md").write_text(job_markdown(job))
    for stale in ("resume.pdf", "resume.log"):
        (folder / stale).unlink(missing_ok=True)
    base = next((Path.home() / ".claude/skills").glob(f"**/{cfg.get('skill', 'resume-builder')}/references/base-resume.tex"), None)
    if base is None:
        return ResumeResult(False, folder, None, "base-resume.tex not found in the resume-builder skill")
    shutil.copyfile(base, folder / "resume.tex")     # Claude tailors this copy instead of writing a resume from scratch

    claude = shutil.which("claude", path=os.pathsep.join(EXTRA_PATH + [os.environ.get("PATH", "")]))
    if not claude:
        return ResumeResult(False, folder, None, "`claude` CLI not found on PATH")
    cmd = [claude, "-p", PROMPT.format(skill=cfg.get("skill", "resume-builder"), name=candidate_name() or "the candidate"),
           "--allowedTools", *ALLOWED_TOOLS,
           "--add-dir", str(Path.home() / ".claude/skills"),
           "--output-format", "json",
           "--strict-mcp-config"]           # no MCP servers/connectors: faster start, no stray connector notes
    if cfg.get("model"):
        cmd += ["--model", str(cfg["model"])]
    env = {**os.environ, "PATH": os.pathsep.join(EXTRA_PATH + [os.environ.get("PATH", "")])}

    log.info("resume: generating for job #%s (%s, %s) in %s", job["id"], job["company"], job["title"], folder)
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=folder, env=env, stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=float(cfg.get("timeout_minutes", 15)) * 60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ResumeResult(False, folder, None, f"timed out after {cfg.get('timeout_minutes', 15)} min")
    (folder / "claude.log").write_bytes(out + b"\n--- stderr ---\n" + err)
    usage.record("resume", job["id"], out)

    summary = ""
    try:
        res = json.loads(out)
        summary = str(res.get("result") or "").strip()
        if res.get("is_error"):
            return ResumeResult(False, folder, None, summary or "Claude run failed (see claude.log)")
    except ValueError:
        summary = err.decode(errors="replace")[-500:] or out.decode(errors="replace")[-500:]

    pdf = folder / "resume.pdf"
    if not pdf.exists():
        return ResumeResult(False, folder, None, summary or "no resume.pdf produced (see claude.log)")
    final = folder / pdf_name(settings, job)
    shutil.copyfile(pdf, final)
    pages = _pages(final)
    if pages and pages > 1:
        summary = f"⚠ PDF is {pages} pages.\n{summary}"
    log.info("resume: done for job #%s → %s", job["id"], final)
    return ResumeResult(True, folder, final, summary)
