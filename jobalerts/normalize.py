"""URL / title / location normalization used by dedup and filtering (research §9)."""
from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "lever-source", "source", "ref", "referrer", "trk", "trackingid",
    "refid", "originalsubdomain", "src", "from", "channel", "recruiter", "rx_source",
}
HOST_ALIASES = {
    "boards.greenhouse.io": "job-boards.greenhouse.io",
    "job-boards.eu.greenhouse.io": "job-boards.greenhouse.io",
}
# Suffixes that point at the same posting: Ashby/Lever "/application" and "/apply".
_APPLY_SUFFIX = re.compile(r"/(application|apply)$")
_WORKDAY_LOCALE = re.compile(r"^/[a-z]{2}-[A-Z]{2}(?=/)")


def normalize_url(u: str) -> str:
    p = urlsplit(u.strip())
    host = p.netloc.lower().removeprefix("www.")
    host = HOST_ALIASES.get(host, host)
    path = p.path
    if "myworkdayjobs.com" in host:
        path = _WORKDAY_LOCALE.sub("", path)
    path = _APPLY_SUFFIX.sub("", path.rstrip("/"))
    qs = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in STRIP_PARAMS]
    return urlunsplit(("https", host, path, urlencode(sorted(qs)), ""))


ATS_ID_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?(?P<org>[\w-]+)/jobs/(?P<id>\d+)")),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_app\?.*?for=(?P<org>[\w-]+).*?token=(?P<id>\d+)")),
    # Greenhouse boards hosted on the company's own domain: instacart.careers/job/?gh_jid=6819435
    ("greenhouse", re.compile(r"^(?:https?://)?(?:www\.)?(?P<org>[^/?#]+)[^?#]*[?&]gh_jid=(?P<id>\d+)")),
    ("ashby", re.compile(r"ashbyhq\.com/(?P<org>[\w.%\-]+)/(?P<id>[0-9a-f]{8}-[0-9a-f-]{27})")),
    ("lever", re.compile(r"lever\.co/(?P<org>[\w.\-]+)/(?P<id>[0-9a-f]{8}-[0-9a-f-]{27})")),
    ("workday", re.compile(r"(?P<org>[\w-]+)\.wd\d+\.myworkdayjobs\.com/.*_(?P<id>[A-Z]*-?\d+(?:-\d+)?)(?:[/?]|$)")),
    ("smartrecruiters", re.compile(r"smartrecruiters\.com/(?P<org>[\w-]+)/(?P<id>\d+)")),
    ("rippling", re.compile(r"ats\.rippling\.com/(?P<org>[\w-]+)/jobs/(?P<id>[0-9a-f-]{36})")),
    ("amazon", re.compile(r"amazon\.jobs/(?:\w{2}/)?jobs/(?P<id>\d+)(?P<org>)")),
]


def ats_identity(url: str | None) -> tuple[str, str, str] | None:
    """('greenhouse', 'anthropic', '5391376008') or None."""
    if not url:
        return None
    for ats, pat in ATS_ID_PATTERNS:
        if m := pat.search(url):
            jid = m["id"]
            if ats == "workday":
                # One requisition posted to several career sites gets _JR37395, _JR37395-1, _JR37395-2 …
                jid = re.sub(r"(?<=\d)-\d{1,2}$", "", jid)
            return ats, (m["org"] or ats).lower(), jid
    return None


_ABBREV = [
    (r"\bswe\b", "software engineer"),
    (r"\bsde\b", "software development engineer"),
    (r"\bml\b", "machine learning"),
    (r"\bsr\.?\b", "senior"),
    (r"\bjr\.?\b", "junior"),
    (r"\bco-op\b", "coop"),
]


def normalize_title(t: str) -> str:
    t = html.unescape(t).lower()
    for pat, rep in _ABBREV:
        t = re.sub(pat, rep, t)
    t = re.sub(r"[^\w\s+#/]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_COMPANY_SUFFIX = re.compile(r"[,\s]+(?:inc|llc|ltd|corp|corporation|co|plc|gmbh|l\.?p)\.?$", re.I)


def company_key(name: str) -> str:
    """'Meta Platforms, Inc.' and 'meta platforms' → 'metaplatforms'; used to match aggregator rows to companies.yaml."""
    return re.sub(r"[^a-z0-9]", "", _COMPANY_SUFFIX.sub("", html.unescape(name or "").strip()).lower())


def fingerprint(company: str, title: str, locations: list[str], season: str | None) -> str:
    key = "|".join([
        re.sub(r"[^a-z0-9]", "", company.lower()),
        normalize_title(title),
        ",".join(sorted(re.sub(r"[^a-z0-9]", "", loc.lower()) for loc in locations)),
        (season or "").lower(),
    ])
    return hashlib.sha256(key.encode()).hexdigest()


def strip_html(s: str | None) -> str | None:
    if not s:
        return s
    s = html.unescape(s)            # Greenhouse double-encodes its content field
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


SEASON_RE = re.compile(r"\b(spring|summer|fall|autumn|winter)\s*(?:of\s*)?'?(20\d{2}|\d{2})\b", re.I)


def extract_season(text: str) -> str | None:
    if m := SEASON_RE.search(text):
        year = m[2] if len(m[2]) == 4 else "20" + m[2]
        season = "Fall" if m[1].lower() == "autumn" else m[1].capitalize()
        return f"{season} {year}"
    return None


# ── Location classification ────────────────────────────────────────────────
US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new hampshire",
    "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina",
    "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota", "TN": "tennessee",
    "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}
US_CITIES = [
    "san francisco", "new york", "nyc", "seattle", "boston", "austin", "los angeles",
    "chicago", "bay area", "silicon valley", "palo alto", "mountain view", "menlo park",
    "sunnyvale", "san jose", "santa clara", "cupertino", "redmond", "bellevue", "cambridge, ma",
    "washington dc", "washington, d.c", "atlanta", "denver", "pittsburgh", "san diego",
    "philadelphia", "miami", "dallas", "houston", "portland", "salt lake", "raleigh",
    "ann arbor", "madison", "minneapolis", "boulder", "brooklyn", "manhattan", "sf",
    "hawthorne", "irvine", "costa mesa", "los gatos", "remote in usa", "remote - us",
    "detroit", "phoenix", "nashville", "cincinnati", "columbus",
]
NON_US = [
    "canada", "toronto", "vancouver", "montreal", "ontario", "british columbia", "quebec",
    "united kingdom", "uk", "london", "england", "scotland", "ireland", "dublin",
    "germany", "berlin", "munich", "france", "paris", "netherlands", "amsterdam", "spain",
    "madrid", "barcelona", "italy", "switzerland", "zurich", "poland", "warsaw", "sweden",
    "stockholm", "denmark", "copenhagen", "norway", "finland", "portugal", "lisbon", "czech",
    "romania", "hungary", "austria", "vienna", "belgium", "israel", "tel aviv",
    "india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "gurgaon",
    "gurugram", "noida", "chennai", "china", "shanghai", "beijing", "shenzhen", "hangzhou",
    "hong kong", "taiwan", "taipei", "japan", "tokyo", "korea", "seoul", "singapore",
    "australia", "sydney", "melbourne", "new zealand", "brazil", "sao paulo", "são paulo",
    "mexico", "argentina", "colombia", "chile", "emea", "apac", "latam", "europe", "uae",
    "dubai", "saudi", "philippines", "vietnam", "indonesia", "malaysia", "thailand",
    "south africa", "nigeria", "kenya", "egypt", "turkey", "istanbul", "costa rica", "bra",
    "deutschland", "bundesweit", "hamburg", "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf", "münchen",
    "ottawa", "calgary", "edmonton", "waterloo", "mississauga", "kolkata", "ahmedabad", "kraków", "krakow",
    "gbr", "deu", "irl", "jpn", "chn", "sgp", "isr", "pol", "fra",
]
# State codes are matched case-sensitively on the raw string: "Austin, TX", "US-CA-…", "US, WA, …"
_STATE_ABBR_RE = re.compile(r"(?:,\s*|\b(?:US|USA)[\s,-]+)(" + "|".join(US_STATES) + r")\b")
_US_RE = re.compile(
    r"\b(united states|usa|u\.s\.a?\.?|us|america|" + "|".join(US_STATES.values()) + ")\\b"
)
_NON_US_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in NON_US) + r")\b")
_CITY_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in US_CITIES) + r")\b")


def classify_location(loc: str) -> str:
    """'us' | 'remote_us' | 'remote' | 'non_us' | 'unknown' for one location string."""
    raw = loc.strip()
    low = raw.lower()
    if not low:
        return "unknown"
    remote = bool(re.search(r"\b(remote|anywhere|virtual|distributed)\b", low))
    # Workday paths like "US-CA-Santa-Clara"; Amazon "US, WA, Seattle"
    us = bool(
        re.match(r"^(us|usa)\b", low)
        or _STATE_ABBR_RE.search(raw)
        or _US_RE.search(low)
        or _CITY_RE.search(low)
    )
    non_us = bool(_NON_US_RE.search(low))
    if us and not (non_us and not re.search(r"\b(united states|usa)\b", low)):
        return "remote_us" if remote else "us"
    if non_us:
        return "non_us"
    if remote:
        return "remote"
    return "unknown"


def location_ok(locations: list[str], allow: set[str]) -> tuple[bool, str]:
    """True if ANY location is in the allowed classes. No locations → unknown."""
    if not locations:
        return ("unknown" in allow), "unknown"
    classes = [classify_location(x) for x in locations]
    for c in ("us", "remote_us", "remote", "unknown"):
        if c in classes and c in allow:
            return True, c
    return False, classes[0]
