"""US-citizenship / clearance / sponsorship screening (PLAN.md §4).

Three outcomes:
  reject   — the posting explicitly requires citizenship or a clearance
  warn     — export-control / "U.S. person" boilerplate without a clear requirement
  unknown  — no description to read; alert anyway, tagged "not verified"
  ok       — description read, nothing found
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CLEARANCE = (r"(?: and (?:maintain|hold|keep))? (?:an? )?(?:active |current )?(?:u\.?s\.? )?(?:government |dod |federal )?"
              r"(?:(?:secret|top secret|ts/sci|ts|q|l)[\s/]*)*(?:security )?clearance")
_HARD = [
    r"must be (?:a )?(?:u\.?s\.?|united states) citizens?",
    r"(?:u\.?s\.?|united states) citizenship (?:is |status is )?(?:required|mandatory|needed)",
    r"requires? (?:u\.?s\.?|united states) citizenship",
    r"(?:only|solely) (?:u\.?s\.?|united states) citizens",
    r"citizenship (?:in|of) the (?:u\.?s\.?|united states) (?:is )?required",
    r"(?:active|current|existing) (?:(?:ts|top secret|secret|ts/sci|public trust)[\s/]*)+(?:security )?clearance (?:is )?(?:required|needed)",
    r"(?:ability|able|eligib\w+|must|required) to (?:obtain|get|acquire|hold|maintain|possess)" + _CLEARANCE,
    r"must (?:obtain|hold|possess|maintain|have)" + _CLEARANCE,
    r"(?:itar|ear)[^.]{0,160}\bmust be an? (?:u\.?s\.?|united states) person",
    r"must be an? (?:u\.?s\.?|united states) person",
    r"(?:u\.?s\.?|united states) citizens?(?: \w+)? only\b",
    r"(?:possess|have|hold) (?:u\.?s\.?|united states) citizenship",
]
_SOFT = [
    r"\bitar\b", r"export control", r"export administration regulations",
    r"(?:u\.?s\.?|united states) person", r"security clearance", r"deemed export",
    r"(?:u\.?s\.?|united states) citizen", r"green card holder", r"permanent resident",
]
_NO_SPONSOR = [
    r"(?:not|unable to|will not|won'?t|cannot|can'?t|does not|do not) (?:be able to )?(?:offer|provide|sponsor|support)[^.]{0,40}(?:visa|sponsorship|work authori[sz]ation)",
    r"(?:visa |immigration )?sponsorship (?:is )?(?:not (?:available|offered|provided)|unavailable)",
    r"no (?:visa )?sponsorship",
    r"without (?:the need for |requiring )?(?:current or future )?(?:visa )?sponsorship",
    r"not eligible for (?:visa )?sponsorship",
]
HARD_RE = re.compile("|".join(f"(?:{p})" for p in _HARD), re.I)
SOFT_RE = re.compile("|".join(f"(?:{p})" for p in _SOFT), re.I)
# Titles like "Software Engineer - Cleared" or "… (TS/SCI)" state the requirement outright.
TITLE_RE = re.compile(r"\b(cleared|clearance|ts\s*/\s*sci|top secret|secret|polygraph|us citizens? only)\b", re.I)
NO_SPONSOR_RE = re.compile("|".join(f"(?:{p})" for p in _NO_SPONSOR), re.I)
# Clearance sentences. A named clearance level ("Secret", "TS/SCI", "Public Trust", a polygraph) or a requirement word
# next to "clearance" makes the sentence a requirement; "preferred" / "a plus" in the same sentence makes it a warning.
_LEVEL_RE = re.compile(r"\b(?:(?:top )?secret|ts\s*/\s*sci|ts|sci|public trust|[ql])(?:[\s/-]+level)?[\s/-]+(?:security )?"
                       r"clearances?\b|\bpolygraph\b(?! protection)", re.I)
_CLEARANCE_WORD_RE = re.compile(r"\bclearances?\b", re.I)
_CLEARANCE_NEED_RE = re.compile(r"\b(?:requires?|required|must|eligib\w*|obtain|possess|hold|maintain|active|current"
                                r"|mandatory|necessary)\b", re.I)
_OTHER_CLEARANCE_RE = re.compile(r"\b(?:customs|tax|medical|sale|price|ground|height|road|credit|payment|trade|"
                                 r"cache|memory|financial)\s+clearances?\b|\bclearance (?:sale|price|rack)", re.I)
# "Minimum Clearance Required to Start: None", "No clearance required"
_NO_CLEARANCE_RE = re.compile(r"clearance[^.\n]{0,40}:\s*(?:none|n/?a)\b|\bno (?:security )?clearance\b", re.I)
_OPTIONAL_RE = re.compile(r"\b(?:preferred|a plus|nice to have|bonus|desired|desirable|not required)\b", re.I)
# Sentence ends: a line break, or . ! ? before a space, except after a single letter ("U.S. citizen", "e.g. ").
_SENTENCE_RE = re.compile(r"\n+|(?<![^\w][A-Za-z])(?<!^[A-Za-z])[.!?]\s+")


@dataclass
class CitizenshipResult:
    status: str               # ok / warn / reject / unknown
    evidence: str | None = None
    no_sponsorship: bool = False

    @property
    def label(self) -> str:
        return {
            "ok": "✅ no citizenship requirement found",
            "warn": "⚠ export-control / US-person wording, check it",
            "reject": "⛔ requires US citizenship or clearance",
            "unknown": "❔ not verified (no description)",
        }[self.status]


def _snippet(text: str, m: re.Match) -> str:
    a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
    return ("…" if a else "") + re.sub(r"\s+", " ", text[a:b]).strip() + ("…" if b < len(text) else "")


def check(description: str | None, sponsorship_field: str | None = None,
          likely_citizenship_company: bool = False, title: str = "") -> CitizenshipResult:
    if m := TITLE_RE.search(title):
        return CitizenshipResult("reject", f"title says “{m[0]}”")
    if sponsorship_field and "citizenship is required" in sponsorship_field.lower():
        return CitizenshipResult("reject", f"Simplify: {sponsorship_field}")
    if not description:
        if likely_citizenship_company:
            return CitizenshipResult("warn", "defense/government contractor; most roles require citizenship")
        return CitizenshipResult("unknown")
    no_sp = bool(NO_SPONSOR_RE.search(description)) or (
        bool(sponsorship_field) and "does not offer sponsorship" in sponsorship_field.lower())
    if m := HARD_RE.search(description):
        return CitizenshipResult("reject", _snippet(description, m), no_sp)
    if hit := _clearance_sentence(description):
        return CitizenshipResult(hit[0], hit[1], no_sp)
    if m := SOFT_RE.search(description):
        return CitizenshipResult("warn", _snippet(description, m), no_sp)
    if likely_citizenship_company:
        return CitizenshipResult("warn", "defense/government contractor", no_sp)
    return CitizenshipResult("ok", None, no_sp)


def _clearance_sentence(text: str) -> tuple[str, str] | None:
    """("reject", sentence) when a sentence requires a clearance, ("warn", sentence) when it only prefers one."""
    warn = None
    for sentence in _SENTENCE_RE.split(text):
        if not _CLEARANCE_WORD_RE.search(sentence) and not _LEVEL_RE.search(sentence):
            continue
        if _NO_CLEARANCE_RE.search(sentence):
            continue
        named = _LEVEL_RE.search(sentence)
        if not named and _OTHER_CLEARANCE_RE.search(sentence):
            continue
        needed = _CLEARANCE_NEED_RE.search(sentence)
        if not (named or needed):
            continue
        clip = _clip_sentence(sentence)
        if _OPTIONAL_RE.search(sentence):
            warn = warn or clip
            continue
        return "reject", clip
    return ("warn", warn) if warn else None


def _clip_sentence(s: str, n: int = 220) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"
