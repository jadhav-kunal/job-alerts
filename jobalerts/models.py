"""The one shape every connector must emit."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedJob:
    source: str                 # e.g. "greenhouse:anthropic", "simplify:internships"
    source_job_id: str          # the source's native id — the dedup backbone
    company: str                # display name
    title: str
    url: str                    # best apply/listing URL the source gives us
    locations: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    description: str | None = None     # plain text when the source includes it
    department: str | None = None
    employment_type: str | None = None  # intern / full_time / unknown …
    compensation: str | None = None
    terms: list[str] = field(default_factory=list)   # ["Summer 2027"] (Simplify)
    category_hint: str | None = None   # Simplify "AI/ML/Data", "Software", …
    level_hint: str | None = None      # "intern" / "new_grad" when the source implies it
    sponsorship: str | None = None     # Simplify sponsorship field
    company_id: str | None = None      # our config id, when the company is tracked
    tier: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class Decision:
    accept: bool
    reason: str
    level: str | None = None       # intern / new_grad / entry
    category: str | None = None    # software / ai_ml / research / data / quant
    flags: list[str] = field(default_factory=list)   # soft warnings shown on the alert
