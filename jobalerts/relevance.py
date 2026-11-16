"""Deterministic title-first relevance rules (research §11).

Pipeline: hard rejects → early-career gate → technical domain → seniority → preferences.
Misses are invisible and duplicates are merely annoying, so anything genuinely ambiguous is
*accepted with a flag* instead of dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Decision, NormalizedJob
from .normalize import extract_season, location_ok, normalize_title

RECRUITING_RE = re.compile(r"\b(recruit\w*|talent acquisition|sourcer|sourcing|university relations|campus relations)\b")
# Non-engineering roles even when the title says "software" or "AI" ("AI Software Sales Representative").
NONTECH_HARD_RE = re.compile(
    r"\b(sales (?:rep\w*|associate|executive|development|manager|specialist|consultant|intern\w*)|account executive"
    r"|scrum master|adjuster|claims (?:analyst|specialist|adjuster|representative)|insurance agent)\b")
EXEC_RE = re.compile(r"\b(director|vice president|vp|head of|chief|cto|ceo|cfo|president|distinguished|partner)\b")

INTERN_RE = re.compile(
    r"\b(intern|interns|internship|internships|coop|co op|apprentice\w*|werkstudent|working student"
    r"|student researcher|student (?:software|engineer|developer|research)|summer (?:analyst|associate|engineer|scholar)"
    r"|trainee|praktikum|stagiaire)\b"
)
PLACEMENT_RE = re.compile(r"\bplacement\b.*\b20\d\d\b|\b20\d\d\b.*\bplacement\b")   # UK "placement" + year only
NEWGRAD_RE = re.compile(
    r"\b(new grad\w*|new college grad\w*|college grad\w*|university grad\w*|recent grad\w*|graduate (?:software|engineer|developer|program|scheme|role)"
    r"|(?:phd|ms|masters|bs|bachelors) grad\w*|entry level|early career|early in career|junior|associate software|associate engineer|associate developer"
    r"|associate (?:machine|data|ml|ai|research)|rotational|rotation program|residency|resident|fellowship|fellows?|university|campus|early talent|emerging talent"
    r"|graduate 20\d\d|20\d\d grad\w*|20\d\d start|class of 20\d\d)\b"
)
# "Software Engineer I", "SDE I", "Engineer 1", "L3", "Level 1", "E3"
LEVEL_ONE_RE = re.compile(r"\b(?:engineer|developer|scientist|analyst|sde|swe)\s*(?:i|1)\b(?!\s*[/-]\s*(?:ii|2))|\b(?:level\s*1|l3|e3|ic1|ic2)\b")

SENIOR_RE = re.compile(
    r"\b(senior|staff|principal|lead|manager|management|architect|expert|sme|head"
    r"|(?:engineer|developer|scientist|sde|swe)\s*(?:ii|iii|iv|v|2|3|4|5|6))\b"
)

AI_ML_RE = re.compile(
    r"\b(machine learning|ai|artificial intelligence|deep learning|llm\w*|genai|generative ai|nlp|natural language"
    r"|computer vision|perception|reinforcement learning|applied scientist|mlops|ml ops|ml infra\w*|inference|foundation models?"
    r"|multimodal|speech recognition|recommender|recommendation systems?|neural|pretraining|post training|interpretability|ai agents?)\b"
)
RESEARCH_RE = re.compile(r"\b(research|researcher|scientist|phd)\b")
DATA_RE = re.compile(r"\b(data scien\w*|data engineer\w*|analytics engineer\w*|data platform|data infrastructure|data analyst|statistic\w*)\b")
QUANT_RE = re.compile(r"\b(quant\w* (?:developer|dev|research\w*|engineer\w*|software|analyst|strateg\w*)|algorithmic trad\w*|trading (?:systems|engineer\w*|developer|infrastructure))\b")
SOFTWARE_RE = re.compile(
    r"\b(software|developer|programmer|swe|sde|backend|back end|frontend|front end|full stack|fullstack"
    r"|web|mobile|ios|android|infrastructure|platform|devops|sre|site reliability|cloud|systems? engineer\w*"
    r"|distributed systems|compiler\w*|kernel|embedded software|firmware|security engineer\w*|application security"
    r"|product engineer\w*|forward deployed|solutions engineer\w*|developer (?:relations|advocate)|test automation"
    r"|qa engineer\w*|sdet|gpu|cuda|robotics software|autonomy software|graphics|game (?:engineer|developer|programmer)"
    r"|computer science|programming)\b"
)
GENERIC_ENG_RE = re.compile(r"\b(engineer|engineering)\b")
HARDWARE_RE = re.compile(
    r"\b(mechanical|electromechanical|electro mechanical|mechatronics|electrical|civil engineer\w*|chemical|structural|manufacturing|hardware|asic|fpga|rtl|vlsi|analog|rf"
    r"|pcb|silicon|circuit|process engineer|materials|propulsion|avionics|thermal|optical|photonics|test technician"
    r"|facilities|construction|industrial|quality engineer|supply chain|packaging|validation engineer|reliability engineer"
    r"|power|battery|manufacturing|technician|field service|network engineer|cabling)\b"
)
NONTECH_RE = re.compile(
    r"\b(sales|account executive|account manager|marketing|legal|counsel|finance|accounting|accountant|tax|audit"
    r"|people|human resources|hr|payroll|benefits|office|executive assistant|administrative|facilities|communications"
    r"|pr|policy|content|copywriter|writer|editor|designer|design|ux|ui|brand|customer|support|success|operations"
    r"|business development|partnerships|procurement|paralegal|compliance|investment banking|real estate|events|trader|trading"
    r"|product manager|product management|program manager|project manager|consult\w*)\b"
)
NONTECH_RESEARCH_RE = re.compile(
    r"\b(market|user|ux|design|clinical|equity|investment|policy|economic|legal|marketing|brand|consumer|survey) research\b"
)

EARLY_CAREER_DESC_RE = re.compile(
    r"(?i)\b(new grad\w*|recent (?:college )?grad\w*|entry[- ]level|early[- ]career|graduating (?:in|by)\s+(?:spring|summer|fall|winter|december|may|june)?\s*20\d\d"
    r"|(?:0|zero)\s*(?:-|–|to)\s*[12]\+?\s*years|up to [12] years|less than [12] years)\b"
)
YEAR_RE = re.compile(r"\b(20\d\d)\b")

CATEGORY_KEYS = ("ai_ml", "research", "data", "quant", "software")


@dataclass
class RelevancePrefs:
    levels: set[str] = field(default_factory=lambda: {"intern", "new_grad"})
    categories: set[str] = field(default_factory=lambda: set(CATEGORY_KEYS))
    seasons: set[str] = field(default_factory=set)      # empty = any season
    allow_locations: set[str] = field(default_factory=lambda: {"us", "remote_us", "remote", "unknown"})
    min_title_year: int = 2026                           # "Summer 2025 Intern" is stale
    accept_unleveled: bool = False                       # mid-level roles with no seniority word
    exclude_title_keywords: list[str] = field(default_factory=list)
    exclude_companies: set[str] = field(default_factory=set)


def _category(t: str, hint: str | None) -> str | None:
    h = (hint or "").lower()
    if QUANT_RE.search(t) or h == "quant":
        return "quant"
    if DATA_RE.search(t):
        return "data"
    if RESEARCH_RE.search(t):
        return "research"
    if AI_ML_RE.search(t):
        return "ai_ml"
    if SOFTWARE_RE.search(t):
        return "software"
    if GENERIC_ENG_RE.search(t) and not HARDWARE_RE.search(t):
        return "software"
    # Simplify's "AI/ML/Data" bucket includes GIS/policy/marketing analysts, so only the
    # software hint is trusted when the title itself carries no technical signal.
    if h in ("software", "software engineering") and not NONTECH_RE.search(t):
        return "software"
    return None


def classify(job: NormalizedJob, prefs: RelevancePrefs) -> Decision:
    t = normalize_title(job.title)
    flags: list[str] = []

    if job.company.lower() in prefs.exclude_companies or (job.company_id or "") in prefs.exclude_companies:
        return Decision(False, "excluded company")
    for kw in prefs.exclude_title_keywords:
        if kw.lower() in t:
            return Decision(False, f"excluded keyword '{kw}'")

    # ── Stage 0: hard rejects
    if RECRUITING_RE.search(t):
        return Decision(False, "recruiting role")
    if NONTECH_RESEARCH_RE.search(t):
        return Decision(False, "non-technical research")
    if NONTECH_HARD_RE.search(t):
        return Decision(False, "non-technical")
    intern = bool(INTERN_RE.search(t) or PLACEMENT_RE.search(t))
    if EXEC_RE.search(t) and not intern:
        return Decision(False, "executive role")

    # ── Stage 1: early-career level
    level: str | None = None
    if intern or job.level_hint == "intern":
        level = "intern"
    elif NEWGRAD_RE.search(t) or LEVEL_ONE_RE.search(t) or job.level_hint == "new_grad":
        level = "new_grad"
    elif job.description and not SENIOR_RE.search(t) and EARLY_CAREER_DESC_RE.search(job.description[:6000]):
        level = "new_grad"
        flags.append("early-career wording found in the description, not the title")
    elif prefs.accept_unleveled and not SENIOR_RE.search(t):
        level = "entry"
        flags.append("no level in title; check experience requirements")
    if level is None:
        return Decision(False, "not early career")
    if level not in prefs.levels and not (level == "entry" and prefs.accept_unleveled):
        return Decision(False, f"level {level} not wanted")

    # ── Stage 2: technical domain
    hint = (job.category_hint or "").lower()
    if hint in ("hardware", "hardware engineering", "product", "product management"):
        if not (SOFTWARE_RE.search(t) or AI_ML_RE.search(t)) or hint.startswith("product"):
            return Decision(False, f"category {hint}")
    category = _category(t, job.category_hint)
    if category is None:
        return Decision(False, "non-technical" if NONTECH_RE.search(t) else "no technical signal")
    if HARDWARE_RE.search(t) and not (SOFTWARE_RE.search(t) or AI_ML_RE.search(t) or RESEARCH_RE.search(t)
                                      or DATA_RE.search(t)):
        return Decision(False, "hardware role")
    if NONTECH_RE.search(t) and not re.search(
            r"\b(software|developer|programmer|(?:web|app|software) development|engineer\w*|swe|sde|data|scientist"
            r"|machine learning|researcher|research (?:intern|engineer\w*|scientist))\b", t):
        return Decision(False, "non-technical")
    if category not in prefs.categories:
        return Decision(False, f"category {category} not wanted")

    # ── Stage 3: seniority is never fatal when an early-career signal exists (the Roblox case)
    if SENIOR_RE.search(t.replace("member of technical staff", "")) and level != "intern":
        if level == "entry":
            return Decision(False, "senior role")
        flags.append("title mixes senior and early-career wording")

    # ── Stage 4: preferences — season, stale year, location
    season = extract_season(job.title)
    terms = set(job.terms) - {"N/A", ""}
    if prefs.seasons:
        if terms and not (terms & prefs.seasons):
            return Decision(False, f"terms {sorted(terms)} not wanted")
        if not terms and season and season not in prefs.seasons:
            return Decision(False, f"season {season} not wanted")
    years = [int(y) for y in YEAR_RE.findall(job.title)]
    if years and max(years) < prefs.min_title_year:
        return Decision(False, f"stale year {max(years)}")

    ok, loc_class = location_ok(job.locations, prefs.allow_locations)
    if not ok:
        return Decision(False, f"location {loc_class}")
    if loc_class == "unknown" and job.locations:
        flags.append("location could not be confirmed as US")

    return Decision(True, f"{level} · {category}", level=level, category=category, flags=flags)
