"""Tag documents and provisions with risk categories, and pull out the
structured facts (deadlines, review frequencies) that make a side-by-side
comparison concrete.

The classifier is rule-based on purpose: every tag carries the exact text that
triggered it, so results are explainable and reviewable. A model-based
classifier can be dropped in later behind the same functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import taxonomy

_FLAGS = re.I

_CAT_PATTERNS: dict[str, list[re.Pattern]] = {
    c.id: [re.compile(k, _FLAGS) for k in c.keywords]
    for c in taxonomy.CATEGORIES
}
_EXP_PATTERNS: dict[str, list[re.Pattern]] = {
    e.id: [re.compile(p, _FLAGS) for p in e.patterns]
    for _cid, e in taxonomy.ALL_EXPECTATIONS
}


@dataclass
class Tag:
    category_id: str
    score: float
    evidence: str
    method: str = "keyword"


def _hits(patterns: list[re.Pattern], text: str) -> list[str]:
    found = []
    for p in patterns:
        m = p.search(text)
        if m:
            found.append(m.group(0))
    return found


def snippet(text: str, needle: str, width: int = 110) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return text[: 2 * width]
    start, end = max(0, i - width), min(len(text), i + len(needle) + width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def matched_keywords(category_id: str, text: str) -> list[str]:
    """The literal keyword matches for one category (used for highlighting)."""
    return _hits(_CAT_PATTERNS.get(category_id, []), text)


def classify_document(title: str, subject: str = "") -> list[Tag]:
    """Document-level tags from metadata (title + regulator's own subject)."""
    tags: dict[str, Tag] = {}
    subject = (subject or "").strip()
    if subject in taxonomy.HE_SUBJECT_TO_CATEGORY:
        cid = taxonomy.HE_SUBJECT_TO_CATEGORY[subject]
        tags[cid] = Tag(cid, 3.0, f"regulator subject: {subject}", "subject")
    for cid, patterns in _CAT_PATTERNS.items():
        hits = _hits(patterns, title)
        if not hits:
            continue
        if cid in tags:
            tags[cid].score += len(hits)
            continue
        tags[cid] = Tag(cid, float(len(hits)), "title: " + ", ".join(hits), "title")
    return sorted(tags.values(), key=lambda t: -t.score)


def classify_provision(text: str, doc_categories: set[str] | None = None,
                       min_hits: int = 2) -> list[Tag]:
    """Provision-level tags from the provision text itself.

    A category needs `min_hits` distinct keyword matches, or one match when
    the parent document is already tagged with that category.
    """
    doc_categories = doc_categories or set()
    tags = []
    for cid, patterns in _CAT_PATTERNS.items():
        hits = _hits(patterns, text)
        needed = 1 if cid in doc_categories else min_hits
        if len(hits) >= needed:
            tags.append(Tag(cid, float(len(hits)), snippet(text, hits[0])))
    return sorted(tags, key=lambda t: -t.score)


def match_expectations(text: str) -> list[tuple[str, str]]:
    """(expectation_id, evidence) pairs found in a provision."""
    out = []
    for eid, patterns in _EXP_PATTERNS.items():
        hits = _hits(patterns, text)
        if hits:
            out.append((eid, snippet(text, hits[0])))
    return out


# --- obligation attributes -------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fourteen": 14, "fifteen": 15, "twenty": 20, "twenty-four": 24,
    "thirty": 30, "forty-eight": 48, "sixty": 60, "seventy-two": 72,
    "ninety": 90,
}
_UNIT_HOURS = {"hour": 1, "day": 24, "week": 168, "month": 730, "year": 8760}

_DEADLINE = re.compile(
    r"\b(?:within|no later than|not later than|not more than)\s+"
    r"(?:a period of\s+)?"
    r"(?P<n>\d{1,3}|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"
    r"(?:\s*\(\d{1,3}\))?\s+"
    r"(?P<kind>business\s+|working\s+|calendar\s+)?"
    r"(?P<unit>hour|day|week|month|year)s?\b",
    _FLAGS)

_FREQUENCY = re.compile(
    r"\b(?:at least\s+(?:once\s+)?(?:a|an|every|per|each)\s+"
    r"(?:year|quarter|month|week|six months|two years|three years)"
    r"|(?:semi-)?annually|quarterly|monthly|once a year|every year"
    r"|every (?:two|three) years)\b",
    _FLAGS)


def extract_deadlines(text: str) -> list[tuple[str, float]]:
    out = []
    for m in _DEADLINE.finditer(text):
        raw_n = m.group("n").lower()
        n = int(raw_n) if raw_n.isdigit() else _NUMBER_WORDS.get(raw_n)
        if n is None:
            continue
        hours = n * _UNIT_HOURS[m.group("unit").lower()]
        if (m.group("kind") or "").strip().lower() in {"business", "working"}:
            hours = hours * 7 / 5  # approximate calendar equivalent
        out.append((" ".join(m.group(0).split()), float(hours)))
    return out


def extract_frequencies(text: str) -> list[str]:
    return sorted({" ".join(m.group(0).lower().split())
                   for m in _FREQUENCY.finditer(text)})
