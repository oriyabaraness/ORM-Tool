"""Layer 2 of the ORM Analysis Standard: the obligation grammar.

Every clause is rewritten into obligation records with the same nine parts
(Force, Addressee, Action, Object, Trigger, Measure, Frequency, Evidence,
Proportionality), so clauses from any country, in any drafting style, can be
compared part by part. A record prints as one RDL line:

    MUST | Institution -> notify(regulator) | object: incident |
    trigger: On an event | measure: within 24 hours | evidence: Report

Rules from the standard that this module enforces:
  * Code the words, not the intent: "shall"/"must" is MUST, "should" is
    SHOULD; a soft word is never upgraded.
  * One obligation per record: "approve the plan and review it annually"
    becomes two records.

Rule-based on purpose (like orm.classify): every value comes from words in
the clause, so a specialist can see why it was coded that way.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from . import classify, rdl

_I = re.I

# --- Force -------------------------------------------------------------------
# Checked in this order; the first family that appears decides.
_FORCE_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("MUST-NOT", re.compile(
        r"\b(?:shall|must|may)\s+not\b|\bcannot\b|"
        r"\b(?:is|are)\s+(?:strictly\s+)?(?:prohibited|forbidden)\b|"
        r"\bprohibited\s+from\b|\bshall\s+refrain\b|"
        r"\b(?:is|are)\s+not\s+(?:permitted|allowed)\b", _I)),
    ("MUST-OR-EXPLAIN", re.compile(
        r"\bcomply\s+or\s+explain\b|\bor\s+(?:shall|must)\s+explain\b|"
        r"\bexplain\s+(?:the\s+)?reasons?\s+for\s+(?:non-?compliance|deviat)", _I)),
    ("MAY", re.compile(
        r"\b(?:shall|will)\s+be\s+(?:entitled|permitted|allowed)\b|"
        r"\b(?:is|are)\s+(?:entitled|permitted|allowed)\s+to\b", _I)),
    ("MUST", re.compile(
        r"\bshall\b|\bmust\b|"
        r"\b(?:is|are)\s+(?:required|obliged|obligated|bound)\s+to\b|"
        r"\b(?:is|are)\s+responsible\s+for\b", _I)),
    ("SHOULD", re.compile(
        r"\bshould\b|\b(?:is|are)\s+expected\s+to\b|"
        r"\b(?:is|are)\s+(?:encouraged|recommended)\b|\bit\s+is\s+recommended\b", _I)),
    ("MAY", re.compile(r"\bmay\b", _I)),
)

# --- Addressee (looked for in the subject, before the modal word) ---------------
_ADDRESSEE_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("Named function", re.compile(
        r"risk management function|chief risk officer|\bCRO\b|"
        r"compliance (?:officer|function|unit|department)|internal audit\w*|"
        r"information security (?:officer|function|manager)|\bCISO\b|"
        r"chief information|reporting officer|\bMLRO\b|\bactuary\b|"
        r"risk (?:manager|officer|committee)|audit committee", _I)),
    ("Board", re.compile(r"\bboard\b", _I)),
    ("Senior management", re.compile(
        r"senior management|general manager|chief executive|\bCEO\b|"
        r"executive management|\bmanagement\b", _I)),
    ("Third party", re.compile(
        r"service provider|outsourc\w*\s+(?:provider|party|company)|\bvendor|"
        r"\bsupplier|third part", _I)),
)
_BY_AGENT = re.compile(r"\bby\s+(?:the\s+)?([^,.;]{3,60})", _I)

# --- Action (fixed verb list) -----------------------------------------------------
_ACTION_RULES: tuple[tuple[str, str], ...] = (
    ("approve", r"approv\w*|ratif\w*|endors\w*"),
    ("notify", r"notif\w*|inform\w*|alert\w*"),
    ("report", r"report\w*|submit\w*|disclos\w*|furnish\w*|send\w*|"
               r"provid(?:e|es|ing)\b|provided\b(?!\s+(?:that|it|they|always|for))"),
    ("test", r"test\w*|drill\w*|exercis\w*|simulat\w*"),
    ("review", r"review\w*|updat\w*|revis\w*|reassess\w*|re-?evaluat\w*"),
    ("monitor", r"monitor\w*|track\w*|oversee\w*|supervis\w*|assess\w*|"
                r"evaluat\w*|measur\w*|identif\w*"),
    ("document", r"document\w*|record\w*|regist\w*"),
    ("retain", r"retain\w*|keep\w*|kept|preserv\w*|stor\w*|archiv\w*"),
    ("restrict", r"restrict\w*|limit\w*|prohibit\w*|refrain\w*|prevent\w*|"
                 r"exceed\w*|avoid\w*"),
    ("establish", r"establish\w*|set\s+up|adopt\w*|put\s+in\s+place|"
                  r"implement\w*|maintain\w*|develop\w*|appoint\w*|"
                  r"have\s+in\s+place|set\b|define\w*|ensure\w*"),
)
_ACTION_RES = [(a, re.compile(rf"\b(?:{p})", _I)) for a, p in _ACTION_RULES]
_ANY_ACTION = "|".join(p for _a, p in _ACTION_RULES if _a != "establish") + \
    r"|establish\w*|adopt\w*|implement\w*|maintain\w*|develop\w*"
# Where one sentence holds two obligations: "... and review it", "; submit ..."
_SPLIT = re.compile(
    rf"(?:\s+and\s+|\s*;\s*|,\s+and\s+)(?:(?:shall|must|should|also|then)\s+)*"
    rf"(?=(?:{_ANY_ACTION})\b)", _I)

# --- Object ---------------------------------------------------------------------
_OBJECT_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("policy", re.compile(r"\bpolic(?:y|ies)\b|\bprocedures?\b", _I)),
    ("plan", re.compile(r"\bplans?\b|\bprogram(?:me)?s?\b|\bstrateg\w+|"
                        r"\barrangements?\b", _I)),
    ("register", re.compile(r"\bregisters?\b|\binventor\w+|\blogs?\b", _I)),
    ("limit", re.compile(r"\blimits?\b|\bthresholds?\b|\bceilings?\b|\bratios?\b", _I)),
    ("system", re.compile(r"\bsystems?\b|\binfrastructure\b|\bapplications?\b|"
                          r"\bnetworks?\b", _I)),
    ("incident", re.compile(r"\bincidents?\b|\bbreach\w*|\bdisruptions?\b|"
                            r"\bfailures?\b|\bfraud\b", _I)),
    ("data", re.compile(r"\bdata\b|\binformation\b|\brecords?\b|\bdocuments?\b", _I)),
    ("contract", re.compile(r"\bcontracts?\b|\bagreements?\b|"
                            r"outsourc\w+\s+arrangements?", _I)),
    ("customer", re.compile(r"\bcustomers?\b|\bclients?\b|\bconsumers?\b|"
                            r"\bdepositors?\b", _I)),
)
_RECIPIENT = (
    ("regulator", re.compile(
        r"\b(?:to|notify|inform|advise|alert)\s+the\s+(?:Supervisor|Central\s+Bank|Bank\s+of\s+Israel|CBRT|BRSA|"
        r"BDDK|regulator|competent\s+authority|authority|Banking\s+Supervision)", _I)),
    ("board", re.compile(r"\bto\s+the\s+board\b", _I)),
    ("customer", re.compile(r"\bto\s+(?:the\s+)?(?:customer|client|consumer)s?\b", _I)),
)

# --- Trigger ----------------------------------------------------------------------
_BEFORE = re.compile(r"\b(?:before|prior\s+to|in\s+advance)\b", _I)
_EVENT = re.compile(
    r"\b(?:in\s+the\s+event\s+(?:of|that)|upon|if|when(?:ever)?|following|"
    r"in\s+case\s+of|where)\b|\bof\s+(?:identifying|becoming\s+aware|detect\w*|"
    r"discover\w*|the\s+occurrence)|\bfrom\s+the\s+(?:date|time)\s+of\b|"
    r"\bany\s+(?:[\w-]+\s+){0,3}(?:incidents?|disruptions?|breach\w*|failures?|"
    r"events?)\b", _I)
_PERIODIC = re.compile(r"\bperiodic\w*|\bregular\s+intervals\b", _I)

# --- Measure ------------------------------------------------------------------------
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|per\s?cent)", _I)
_AMOUNT = re.compile(r"(?:USD|JOD|JD|NIS|ILS|TRY|TL|\$|€)\s?\d[\d,.]*"
                     r"(?:\s*(?:million|billion|thousand))?", _I)

# --- Frequency ----------------------------------------------------------------------
_CONTINUOUS = re.compile(r"\bcontinuous(?:ly)?\b|\bon\s+an\s+ongoing\s+basis\b|"
                         r"\bat\s+all\s+times\b|\bongoing\b", _I)
_FREQ_LABELS: tuple[tuple[re.Pattern, str, float], ...] = (
    (re.compile(r"semi-?annual|six\s+months", _I), "Semi-annually", 6),
    (re.compile(r"two\s+years", _I), "Every 2 years", 24),
    (re.compile(r"three\s+years", _I), "Every 3 years", 36),
    (re.compile(r"annual|year", _I), "Annually", 12),
    (re.compile(r"quarter", _I), "Quarterly", 3),
    (re.compile(r"month", _I), "Monthly", 1),
    (re.compile(r"week", _I), "Weekly", 0.25),
)

# --- Evidence -----------------------------------------------------------------------
_EVIDENCE_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("Minutes", re.compile(r"\bminutes\b", _I)),
    ("Test result", re.compile(r"\btest\s+results?\b|\bresults?\s+of\s+(?:the\s+)?"
                               r"(?:test|drill|exercise)", _I)),
    ("Attestation", re.compile(r"\battest\w*|\bcertif\w*|\bdeclaration\b|"
                               r"\bconfirm\w*\s+in\s+writing", _I)),
    ("Register entry", re.compile(r"\bregister\b|\blog\b|\brecord\s+of\b|"
                                  r"\bkeep\s+(?:a\s+)?records?\b", _I)),
    ("Report", re.compile(r"\b(?:a|the|written|annual|quarterly|detailed)\s+report\b|"
                          r"\broot\s+cause\s+analysis\b|\banalysis\b", _I)),
    ("Written record", re.compile(r"\bin\s+writing\b|\bwritten\b|\bdocumented\b", _I)),
)

# --- Proportionality ------------------------------------------------------------------
_PROPORTION_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("By risk profile", re.compile(r"proportion\w*|commensurate|nature,?\s+scale\s+and\s+"
                                   r"complexity|risk\s+profile|risk-based", _I)),
    ("By size", re.compile(r"systemically\s+important|\bD-SIBs?\b|"
                           r"\b(?:small|large)(?:er)?\s+(?:banks?|institutions?)|"
                           r"total\s+assets\s+(?:of|exceeding)", _I)),
    ("By licence type", re.compile(r"islamic\s+bank|microfinance|money\s+exchange|"
                                   r"payment\s+(?:service\s+)?(?:institution|provider)s?|"
                                   r"electronic\s+money\s+institution|e-money|"
                                   r"exchange\s+compan", _I)),
)

_SENTENCE = re.compile(r"(?<=[.;])\s+(?=[A-Z(\"'])")


@dataclass
class Record:
    """One obligation record: the nine parts of the grammar, plus the
    control type (Layer 3) and the sentence it was read from."""
    force: str
    addressee: str
    action: str | None
    target: str | None
    object: str | None
    trigger: str
    measure: str | None
    measure_hours: float | None
    frequency: str | None
    frequency_months: float | None
    evidence: str | None
    proportionality: str
    control_type: str | None
    sentence: str

    def notation(self) -> str:
        """The record as one RDL line."""
        on = self.target or self.object
        act = f"{self.action or '—'}({on})" if on else (self.action or "—")
        parts = [self.force, f"{self.addressee} -> {act}"]
        for label, value in (("object", self.object),
                             ("trigger", None if self.trigger == "Always" else self.trigger),
                             ("measure", self.measure), ("frequency", self.frequency),
                             ("evidence", self.evidence),
                             ("scope", None if self.proportionality == "All institutions"
                              else self.proportionality)):
            if value:
                parts.append(f"{label}: {value}")
        return " | ".join(parts)

    def as_row(self) -> dict:
        return asdict(self)


def _first(rules, text: str):
    """The earliest-matching label among (label, pattern) rules."""
    best = None
    for label, pattern in rules:
        m = pattern.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), label)
    return best[1] if best else None


def force_of(sentence: str) -> tuple[str, int, int] | None:
    """(force, start, end) of the modal wording that decides the force."""
    for force, pattern in _FORCE_RULES:
        m = pattern.search(sentence)
        if m:
            return force, m.start(), m.end()
    return None


def _addressee(subject: str, predicate: str) -> str:
    if re.match(r"\s*be\s+\w+ed\b", predicate, _I):        # passive voice
        agent = _BY_AGENT.search(predicate)
        if agent:
            found = _first(_ADDRESSEE_RULES, agent.group(1))
            if found:
                return found
    return _first(_ADDRESSEE_RULES, subject[-160:]) or "Institution"


def _action(segment: str, force: str) -> str | None:
    if force == "MUST-NOT":
        return "restrict"
    best = None
    for action, pattern in _ACTION_RES:
        for m in pattern.finditer(segment):
            if action == "establish" and m.group(0).lower().startswith("ensur"):
                # "ensure that X is tested": keep looking for the real verb
                if best is None:
                    best = (10_000 + m.start(), action)
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), action)
            break
    return best[1] if best else None


def _trigger(segment: str, sentence: str, has_frequency: bool) -> str:
    for text in (segment, sentence):
        if _BEFORE.search(text):
            return "Before an action"
        if _EVENT.search(text):
            return "On an event"
    if has_frequency or _PERIODIC.search(segment):
        return "On a schedule"
    return "Always"


def _measure(segment: str) -> tuple[str | None, float | None]:
    deadlines = classify.extract_deadlines(segment)
    if deadlines:
        return deadlines[0]
    for pattern in (_PERCENT, _AMOUNT):
        m = pattern.search(segment)
        if m:
            return " ".join(m.group(0).split()), None
    return None, None


def _frequency(segment: str) -> tuple[str | None, float | None]:
    if _CONTINUOUS.search(segment):
        return "Continuous", 0.0
    for raw in classify.extract_frequencies(segment):
        for pattern, label, months in _FREQ_LABELS:
            if pattern.search(raw):
                return label, months
    return None, None


def _control_type(action: str | None, addressee: str, trigger: str,
                  obj: str | None) -> str | None:
    if action is None:
        return None
    if action == "approve" or (addressee in ("Board", "Senior management")
                               and action in ("establish", "review")):
        return "Governance"
    if action == "notify" or (action == "report" and
                              (trigger == "On an event" or obj == "incident")):
        return "Corrective"
    if action in ("establish", "restrict", "retain"):
        return "Preventive"
    return "Detective"


def parse_sentence(sentence: str) -> list[Record]:
    sentence = " ".join(sentence.split())
    found = force_of(sentence)
    if not found:
        return []
    force, start, end = found
    subject, predicate = sentence[:start], sentence[end:]
    addressee = _addressee(subject, predicate)
    proportionality = _first(_PROPORTION_RULES, sentence) or "All institutions"
    segments = [s for s in _SPLIT.split(predicate) if s.strip()] or [predicate]
    records = []
    for segment in segments:
        action = _action(segment, force)
        obj = (_first(_OBJECT_RULES, segment) or _first(_OBJECT_RULES, predicate)
               or _first(_OBJECT_RULES, subject))
        target = _first(_RECIPIENT, segment) or _first(_RECIPIENT, predicate)
        measure, hours = _measure(segment)
        frequency, months = _frequency(segment)
        trigger = _trigger(segment, sentence, frequency is not None)
        if frequency is None and trigger == "On an event":
            frequency = "Per event"
        records.append(Record(
            force=force, addressee=addressee, action=action, target=target,
            object=obj, trigger=trigger, measure=measure, measure_hours=hours,
            frequency=frequency, frequency_months=months,
            evidence=_first(_EVIDENCE_RULES, segment),
            proportionality=proportionality,
            control_type=_control_type(action, addressee, trigger, obj),
            sentence=sentence))
    return records


def parse(text: str) -> list[Record]:
    """Every obligation record in a clause, in reading order."""
    records: list[Record] = []
    for sentence in _SENTENCE.split(" ".join((text or "").split())):
        if len(sentence) < 12:
            continue
        records.extend(parse_sentence(sentence))
    return records


assert set(rdl.FORCES) >= {f for f, _ in _FORCE_RULES}
