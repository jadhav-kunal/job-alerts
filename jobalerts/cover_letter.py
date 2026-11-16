"""Cover letter for one job: Claude Code writes the text from the job posting and the resume-builder experience bank,
then this module lays it out with config/cover_letter_template.tex (the same layout as your earlier letters) and
compiles it with pdflatex. Claude only writes text, so the layout and contact line never drift.

Runs on the host next to the resume bot (needs the `claude` login, the skill files and TeX).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import yaml

from . import usage
from .config import ROOT, Settings
from .resume import EXTRA_PATH, ResumeResult, _pages, _slug, job_folder, job_markdown

log = logging.getLogger(__name__)

ALLOWED_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "WebFetch"]
TEMPLATE = ROOT / "config/cover_letter_template.tex"
PROFILE = ROOT / "config/profile.yaml"

PROMPT = """You are drafting a cover letter for {name}, for the job described in job.md (current directory).
Nobody is watching this run, so do not ask questions; make the best letter you can from what is available.

Read first:
1. job.md: the posting. If it says the description is missing or partial, use WebFetch on the apply URL to read it.
2. {skill_md}: the "Authoritative Updates" section (publications, projects, status notes) overrides older facts.
3. {bank}: {name}'s experience bank. Every claim in the letter must come from these two files.
4. {examples}: letters {name} has sent before (if any). Match their voice and structure, not their sentences.

What the letter must do:
- Four paragraphs, 280 to 380 words in total, so it fits one page.
- Paragraph 1: the exact role title and company, and one specific reason this team's product or problem interests
  them, taken from the posting (what they build, a technical challenge it names). Do not open with "I am writing to
  express my interest" or "I am excited to apply"; start with the substance.
- Paragraph 2: their strongest directly relevant experience for this posting (jobs, research, open source), with
  one or two concrete results that appear in the experience bank.
- Paragraph 3: a project or publication that matches the role's technical focus (for AI/ML or research roles prefer
  the publications and research projects; for product or full-stack roles prefer shipped systems), and what it shows
  about how they work.
- Paragraph 4: a short, specific close that ties their background to what the team needs. No "I look forward to the
  possibility of discussing how my background and interests align with your team's needs."
- Mention their current or most recent degree (school, degree, graduation date from the experience bank) once.
- Internship postings: if the posting names a term, dates or location, state their availability for it only if job.md
  or the bank supports it; otherwise do not promise availability.
- Never invent metrics, employers, tools, dates or motivations. If the bank lacks something the posting wants, leave
  it out rather than claim it.
- No em dashes or en dashes anywhere. Plain sentences, no bullet points, no markdown, no bold.
- Use the hiring manager's or team's name only if the posting gives one; otherwise the salutation is "Hiring Team".

Write cover_letter.json in the current directory, exactly this shape:
{{"salutation": "Hiring Team", "company_line": "<company name as the posting writes it>",
  "paragraphs": ["...", "...", "...", "..."],
  "notes": "<one or two lines: what you emphasised, anything {name} should check>"}}

Then reply with the notes only.
"""


def _skill_dir() -> Path | None:
    """The resume-builder skill folder (synced skills live under a generated id)."""
    hits = sorted((Path.home() / ".claude/skills").glob("**/resume-builder/SKILL.md"))
    return hits[0].parent if hits else None


def _bank_file(skill: Path) -> Path:
    """The experience bank in the skill's references/: the first *context*.md that is not the template."""
    hits = [p for p in sorted((skill / "references").glob("*context*.md")) if p.name != "context-template.md"]
    return hits[0] if hits else skill / "references/context.md"


def _examples_file(folder: Path) -> Path:
    """Plain text of a few earlier letters, extracted once and cached in data/."""
    cache = ROOT / "data/cover_letter_examples.txt"
    if cache.exists():
        return cache
    found = sorted((Path.home() / "Documents").glob("Cover_Letter___*.pdf")) + \
        sorted((Path.home() / "Downloads").glob("Cover_Letter___*.pdf"), key=lambda p: -p.stat().st_mtime)
    texts = []
    for pdf in found[:4]:
        try:
            out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                                 timeout=20, env={"PATH": os.pathsep.join(EXTRA_PATH + [os.environ.get("PATH", "")])})
            texts.append(f"===== {pdf.name}\n{out.stdout.strip()}")
        except (OSError, subprocess.TimeoutExpired):
            continue
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n\n".join(texts) or "(no earlier letters found)")
    return cache


def profile() -> dict:
    return yaml.safe_load(PROFILE.read_text()) if PROFILE.exists() else {}


def _name() -> str:
    n = profile().get("name") or {}
    return " ".join(x for x in (n.get("first"), n.get("last")) if x) or "the candidate"


def pdf_name(job: dict) -> str:
    p = profile().get("name") or {}
    prefix = f"{p.get('first', 'Cover')}_{p.get('last', 'Letter')}_Cover_Letter"
    return f"{prefix}_{_slug(job['company'], 30)}.pdf"


_TEX_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def tex_escape(s: str) -> str:
    s = re.sub(r"\s*[—–]\s*", ", ", s)                       # no dashes, as in the resume rules
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = "".join(_TEX_ESCAPES.get(c, c) for c in s)
    return re.sub(r'"([^"]*)"', r"``\1''", s)


def render(letter: dict, prof: dict, today: date | None = None) -> tuple[str, str]:
    """(LaTeX source, plain text) for a letter dict from cover_letter.json."""
    today = today or date.today()
    name = " ".join(x for x in ((prof.get("name") or {}).get("first"), (prof.get("name") or {}).get("last")) if x)
    links = prof.get("links") or {}
    contact = [(prof.get("email"), f"mailto:{prof.get('email')}"), (prof.get("phone"), None)]
    for label, key in (("Github", "github"), ("Linkedin", "linkedin")):
        if url := links.get(key):
            contact.append((f"{label}/{url.rstrip('/').rsplit('/', 1)[-1]}", url))
    if url := links.get("portfolio"):
        contact.append((url.split("://", 1)[-1].removeprefix("www.").rstrip("/"), url))
    contact_tex = " \\textbar{} ".join(
        (f"\\href{{{u}}}{{{tex_escape(t)}}}" if u else tex_escape(t)) for t, u in contact if t)
    when = f"{today.strftime('%B')} {today.day}, {today.year}"
    paragraphs = [p.strip() for p in letter.get("paragraphs") or [] if p and p.strip()]
    tex = (TEMPLATE.read_text()
           .replace("<<NAME>>", tex_escape(name))
           .replace("<<CONTACT>>", contact_tex)
           .replace("<<COMPANY>>", tex_escape(letter.get("company_line") or ""))
           .replace("<<DATE>>", when)
           .replace("<<SALUTATION>>", tex_escape(letter.get("salutation") or "Hiring Team"))
           .replace("<<BODY>>", "\n\n".join(tex_escape(p) for p in paragraphs)))
    plain = "\n\n".join([f"Dear {letter.get('salutation') or 'Hiring Team'},", *paragraphs, f"Sincerely,\n{name}"])
    return tex, re.sub(r"\s*[—–]\s*", ", ", plain)


def existing(settings: Settings, job: dict) -> Path | None:
    f = job_folder(settings, job) / pdf_name(job)
    return f if f.exists() else None


async def generate(settings: Settings, job: dict) -> ResumeResult:
    cfg = settings.resume
    folder = job_folder(settings, job)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.md").write_text(job_markdown(job))
    for stale in ("cover_letter.json", "cover_letter.pdf"):
        (folder / stale).unlink(missing_ok=True)

    skill = _skill_dir()
    if skill is None:
        return ResumeResult(False, folder, None, "resume-builder skill not found under ~/.claude/skills")
    path = os.pathsep.join(EXTRA_PATH + [os.environ.get("PATH", "")])
    claude = shutil.which("claude", path=path)
    if not claude:
        return ResumeResult(False, folder, None, "`claude` CLI not found on PATH")
    prompt = PROMPT.format(skill_md=skill / "SKILL.md", bank=_bank_file(skill), name=_name(),
                           examples=_examples_file(folder))
    cmd = [claude, "-p", prompt, "--allowedTools", *ALLOWED_TOOLS, "--add-dir", str(skill),
           "--add-dir", str(ROOT / "data"), "--output-format", "json", "--strict-mcp-config"]
    if cfg.get("model"):
        cmd += ["--model", str(cfg["model"])]

    log.info("cover letter: generating for job #%s (%s, %s)", job["id"], job["company"], job["title"])
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=folder, env={**os.environ, "PATH": path},
                                                stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=float(cfg.get("timeout_minutes", 15)) * 60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ResumeResult(False, folder, None, "timed out")
    (folder / "cover_letter_claude.log").write_bytes(out + b"\n--- stderr ---\n" + err)
    usage.record("cover_letter", job["id"], out)
    notes = ""
    try:
        res = json.loads(out)
        notes = str(res.get("result") or "").strip()
        if res.get("is_error"):
            return ResumeResult(False, folder, None, notes or "Claude run failed (see cover_letter_claude.log)")
    except ValueError:
        notes = err.decode(errors="replace")[-400:]

    try:
        letter = json.loads((folder / "cover_letter.json").read_text())
    except (OSError, ValueError) as e:
        return ResumeResult(False, folder, None, f"no usable cover_letter.json ({e}). {notes}")
    tex, plain = render(letter, profile())
    (folder / "cover_letter.tex").write_text(tex)
    (folder / "cover_letter.txt").write_text(plain + "\n")
    proc = await asyncio.create_subprocess_exec(
        "pdflatex", "-interaction=nonstopmode", "-halt-on-error", "cover_letter.tex", cwd=folder,
        env={**os.environ, "PATH": path}, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    pdf = folder / "cover_letter.pdf"
    if not pdf.exists():
        return ResumeResult(False, folder, None, "pdflatex failed (see cover_letter.log); the text is in cover_letter.txt")
    final = folder / pdf_name(job)
    shutil.copyfile(pdf, final)
    if (pages := _pages(final)) and pages > 1:
        notes = f"⚠ {pages} pages; trim it before sending.\n{notes}"
    log.info("cover letter: done for job #%s → %s", job["id"], final)
    return ResumeResult(True, folder, final, notes)
