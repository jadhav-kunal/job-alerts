"""Answers for the application questions the extension could not fill from profile.yaml ("✍️ Answer the rest").

The extension sends each open question (label, help text, options). Claude Code, on your subscription, reads the
posting, the experience bank and profile.yaml itself (and can WebFetch a missing posting) and writes answers.json.
The extension fills the answers in and outlines them in blue for review.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path

from . import usage
from .config import ROOT, Settings
from .cover_letter import PROFILE, _skill_dir
from .resume import EXTRA_PATH, candidate_name, job_folder, job_markdown

log = logging.getLogger(__name__)

ALLOWED_TOOLS = ["Read", "Write", "Glob", "Grep", "WebFetch"]

PROMPT = """Answer the open questions of a job application for {name}. Nobody is watching this run, so do
not ask anything; answer what you can and leave the rest null.

Follow the application-answers skill: read {answers_skill} and the context files it lists in its references/
folder (they link to the resume-builder skill and profile.yaml) before writing anything.

This run's files, in the current directory:
1. job.md: the job. If the description is missing or short, use WebFetch on the apply URL to read the posting.
2. questions.json: the questions still empty on the form. Each has a key, label, help text, type, "options" for
   choices, and "max_length" (characters) / "max_words" when the form states a limit. Stay under every limit.

Write answers.json in the current directory in the shape the skill's "Output for the job-alerts helper" section
gives, then reply with the notes only.
"""


def answers_skill_dir() -> Path | None:
    """The application-answers skill (~/.claude/skills/application-answers): answer rules plus links to the context."""
    hits = sorted((Path.home() / ".claude/skills").glob("**/application-answers/SKILL.md"))
    return hits[0].parent if hits else None


def run_folder(settings: Settings, job: dict | None, run_id: str) -> Path:
    if job:
        return job_folder(settings, job) / "answers" / run_id
    return ROOT / "data/answers" / run_id


def page_job(url: str, referrer: str, title: str) -> str:
    """job.md for a page that is not one of the alerts: Claude reads the posting itself."""
    return "\n".join([f"# {title or 'Job application'}", "", f"- Apply URL: {url}",
                      *( [f"- Job page: {referrer}"] if referrer else []), "",
                      "The description is not stored; WebFetch the job page (or the apply URL) to read it."]) + "\n"


def fit_to(text: str, max_length: int | None = None, max_words: int | None = None) -> str:
    """Cut an answer to the form's limits at a sentence end (else a word end); same rule as fitTo in content.js."""
    t = text
    if max_words and len(t.split()) > max_words:
        t = " ".join(t.split()[:max_words])
    if max_length and len(t) > max_length:
        t = t[:max_length]
    if t == text:
        return text
    m = re.match(r"[\s\S]*[.!?](?=\s|$)", t)
    return (m.group(0) if m and len(m.group(0)) >= len(t) / 2 else re.sub(r"\s+\S*$", "", t)).strip()


def clean_answers(data: dict, questions: list[dict]) -> list[dict]:
    """Only known keys; a choice answer must be one of the options (matched case-insensitively), else null; a text
    answer over the form's stated limit is cut to fit and flagged "shortened"."""
    by_key = {q["key"]: q for q in questions}
    out = []
    for a in data.get("answers", []):
        if not isinstance(a, dict) or a.get("key") not in by_key:
            continue
        ans, q = a.get("answer"), by_key[a["key"]]
        if isinstance(ans, str):
            ans = re.sub(r"\s*[\u2014\u2013]\s*", ", ", ans).strip() or None
        if ans is not None and q.get("type") == "choice":
            ans = next((o for o in q.get("options") or [] if o.strip().lower() == str(ans).strip().lower()), None)
        if isinstance(ans, str) and (q.get("max_length") or q.get("max_words")):
            fitted = fit_to(ans, q.get("max_length"), q.get("max_words"))
            if fitted != ans:
                log.info("answers: %s was %d chars / %d words, over %s; cut to %d chars", a["key"], len(ans),
                         len(ans.split()), {k: q.get(k) for k in ("max_length", "max_words")}, len(fitted))
                out.append({"key": a["key"], "answer": fitted, "shortened": True})
                continue
        out.append({"key": a["key"], "answer": ans})
    return out


async def generate(settings: Settings, job: dict | None, questions: list[dict], run_id: str,
                   url: str = "", referrer: str = "", title: str = "") -> dict:
    folder = run_folder(settings, job, run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.md").write_text(job_markdown(job) if job else page_job(url, referrer, title))
    (folder / "questions.json").write_text(json.dumps(questions, indent=2))

    skill, answers_skill = _skill_dir(), answers_skill_dir()
    if skill is None or answers_skill is None:
        return {"status": "error", "error": "resume-builder or application-answers skill not found under ~/.claude/skills"}
    return await _claude(settings, job, questions, folder, skill, answers_skill, url)


async def _claude(settings: Settings, job: dict | None, questions: list[dict], folder: Path, skill: Path,
                  answers_skill: Path, url: str) -> dict:
    path = os.pathsep.join(EXTRA_PATH + [os.environ.get("PATH", "")])
    claude = shutil.which("claude", path=path)
    if not claude:
        return {"status": "error", "error": "`claude` CLI not found on PATH"}
    prompt = PROMPT.format(answers_skill=answers_skill / "SKILL.md", name=candidate_name() or "the candidate")
    # The skill's references/ are links into the resume-builder skill and config/, so all three folders are readable.
    cmd = [claude, "-p", prompt, "--allowedTools", *ALLOWED_TOOLS, "--add-dir", str(answers_skill), "--add-dir", str(skill),
           "--add-dir", str(PROFILE.parent), "--output-format", "json", "--strict-mcp-config"]
    model = settings.resume.get("answers_model") or settings.resume.get("model")
    if model:
        cmd += ["--model", str(model)]

    log.info("answers: %d question(s) for %s", len(questions), f"job #{job['id']}" if job else url)
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=folder, env={**os.environ, "PATH": path},
                                                stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=8 * 60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"status": "error", "error": "timed out"}
    (folder / "answers_claude.log").write_bytes(out + b"\n--- stderr ---\n" + err)
    used = usage.record("answers", job["id"] if job else None, out)
    try:
        res = json.loads(out)
        if res.get("is_error"):
            return {"status": "error", "error": str(res.get("result") or "Claude run failed")[:300]}
    except ValueError:
        pass
    try:
        data = json.loads((folder / "answers.json").read_text())
    except (OSError, ValueError) as e:
        return {"status": "error", "error": f"no usable answers.json ({e})"}
    answers = clean_answers(data, questions)
    notes = str(data.get("notes") or "")[:400]
    short = [a["key"] for a in answers if a.get("shortened")]
    if short:
        notes += f" Shortened to fit the form's limit (read them): {', '.join(short)}."
    return {"status": "done", "answers": answers, "notes": notes,
            "folder": str(folder), "usage": used, "provider": "Claude"}
