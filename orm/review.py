"""Clause-level comparison for an operational-risk coordinator.

Reads two clauses and separates what the text states from what it does not.
A difference in the indexed requirements is not a compliance gap: the bank's
own controls are not in the index. A stricter clause does not satisfy the
other jurisdiction. Costs, penalties and severity are never invented.
"""
from __future__ import annotations

import re

from .classify import extract_deadlines, extract_frequencies

_MODAL = re.compile(
    r"\b(?:shall|must|should|is required to|are required to|"
    r"is expected to|are expected to)\b",
    re.I)
_ESTABLISH = re.compile(
    r"\b(?:establishes|establish)\s+(?P<object>[^.]{8,160})", re.I)
_ACTORS = (
    (re.compile(r"board of directors|\bthe board\b|\bboard\b", re.I), "the board"),
    (re.compile(r"senior management", re.I), "senior management"),
    (re.compile(r"chief risk officer", re.I), "the chief risk officer"),
    (re.compile(r"risk management function", re.I), "the risk management function"),
    (re.compile(r"compliance officer", re.I), "the compliance officer"),
    (re.compile(r"compliance function", re.I), "the compliance function"),
    (re.compile(r"internal audit", re.I), "internal audit"),
    (re.compile(r"supervisor", re.I), "the supervisor"),
    (re.compile(r"banking corporations?|\bbanks?\b", re.I), "the bank"),
    (re.compile(r"\bthe institution\b", re.I), "the institution"),
)
_VERBS = {
    "assess", "analyze", "analyse", "approve", "develop", "document", "ensure",
    "establish", "include", "maintain", "meet", "notify", "refer", "report",
    "review", "submit", "take", "keep", "record", "monitor", "test", "update",
}
NE = "Not established"
_EXPLICIT = {"shall", "must", "is required to", "are required to"}

_THEMES = (
    ("People", re.compile(r"\b(?:board|senior management|staff|employees|training)\b", re.I)),
    ("Processes", re.compile(r"\b(?:process(?:es)?|procedure|policy|approval)\b", re.I)),
    ("Systems", re.compile(r"\b(?:systems?|information technology|cyber)\b", re.I)),
    ("External events", re.compile(r"\b(?:incident|disruption|disaster|climate|external event)\b", re.I)),
    ("Third parties", re.compile(r"\b(?:third[- ]part\w*|outsourc\w*|vendor|cloud provider|supplier)\b", re.I)),
)
_RESILIENCE = re.compile(
    r"\b(?:business continuity|disaster recovery|impact tolerance|"
    r"stress[- ]test\w*|incident management)\b", re.I)
_ENTITIES = (
    (re.compile(r"banking corporations?", re.I), "banking corporations"),
    (re.compile(r"microfinance compan\w*", re.I), "microfinance companies"),
    (re.compile(r"\bbanks\b", re.I), "banks"),
    (re.compile(r"\bthe institution\b", re.I), "the institution"),
)

_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "by",
    "from", "that", "this", "these", "those", "their", "its", "into", "as", "at",
    "be", "is", "are", "when", "where", "which", "such", "any", "all", "not",
    "than", "within", "under", "shall", "must", "should", "banking",
    "corporation", "corporations", "bank", "banks", "also", "each", "every",
    "after", "before", "during", "through", "about", "over", "into",
}


def coordinator_notes(home_name: str, home_text: str, other_name: str,
                      other_text: str | None = None, *,
                      assessed: bool = True) -> dict:
    """Short form of :func:`analyst_brief` for the clause column."""
    brief = analyst_brief(home_name, home_text, other_name, other_text,
                          assessed=assessed)
    return {"status": brief["status"],
            "points": [item["text"] for item in brief["executive"]]}


def analyst_brief(home_name: str, home_text: str, other_name: str,
                  other_text: str | None = None, *, assessed: bool = True,
                  home_regulator: str = "", other_regulator: str = "",
                  home_published: str = "", other_published: str = "",
                  home_ref: str = "", other_ref: str = "") -> dict:
    """The six-part clause comparison. Missing facts stay 'Not established'."""
    home_text = home_text or ""
    if not assessed:
        return _pack(
            "not_assessed",
            [f"Not assessed. {other_name} has no indexed text in this "
             "category, so there is no difference to review yet."],
            home_name, home_text, other_name, None,
            home_regulator, other_regulator, home_published, other_published,
            home_ref, other_ref, [], [], [])

    home_items = _obligations(home_text)
    if not other_text:
        named = _named(home_items, home_text)
        findings = [
            f"{home_name} requires {named}.",
            f"No comparable clause was found in {other_name}. "
            "This is a difference in the indexed requirements, not a "
            "compliance gap. The bank's controls are Not established.",
        ]
        return _pack(
            "unmatched", findings, home_name, home_text, other_name, "",
            home_regulator, other_regulator, home_published, other_published,
            home_ref, other_ref, home_items, [], [])

    other_text = other_text or ""
    other_items = _obligations(other_text)
    home_only = _only(home_items, other_items)
    other_only = _only(other_items, home_items)
    shared = [item for item in home_items
              if any(_same(item["action"], other["action"]) for other in other_items)]
    timing = _timing(home_name, home_text, other_name, other_text)
    if timing and "sets the time" in timing:
        timing += (" Meeting the shorter time does not, by itself, satisfy "
                   "the other jurisdiction.")
    owner = _owner(home_name, home_items, other_name, other_items)
    force = _force_note(home_name, shared, other_name, other_items)
    lead = _shared_lead(shared, home_only or other_only or force)

    if not home_items and not other_items:
        findings = [
            f"{home_name} says: {_topic(home_text)}.",
            f"{other_name} says: {_topic(other_text)}.",
            "Neither clause states an obligation with shall, must or should. "
            "Whether either text creates a duty is Not established.",
            _boundary(False),
        ]
        return _pack(
            "differs", findings, home_name, home_text, other_name, other_text,
            home_regulator, other_regulator, home_published, other_published,
            home_ref, other_ref, [], [], [])

    substance = [p for p in (
        lead,
        _side_sentence(home_name, home_only, other_name, "does not state"),
        _side_sentence(other_name, other_only, home_name, "does not state"),
        timing, owner, force,
    ) if p]
    aligned = not substance
    if aligned:
        named = _join_items((shared or home_items or other_items)[:2])
        findings = [
            f"Both countries require {named}.",
            "A similar obligation does not mean one control satisfies both "
            "jurisdictions. The bank's controls are Not established.",
        ]
        status = "aligned"
    else:
        findings = substance[:4] + [_boundary(False)]
        status = "differs"
    return _pack(
        status, findings, home_name, home_text, other_name, other_text,
        home_regulator, other_regulator, home_published, other_published,
        home_ref, other_ref, home_only, other_only, shared)


def _pack(status, findings, home_name, home_text, other_name, other_text,
          home_regulator, other_regulator, home_published, other_published,
          home_ref, other_ref, home_only, other_only, shared) -> dict:
    other_known = other_text is not None
    return {
        "status": status,
        "executive": [{"text": text} for text in findings[:5]],
        "matrix": _matrix(
            home_name, home_text or "", other_name, other_text,
            home_regulator, other_regulator, home_published, other_published,
            home_ref, other_ref, other_known),
        "risk": _risk(home_text or "", other_text if other_known else ""),
        "shared": [_phrase(item) for item in shared[:4]],
        "home_only": [_phrase(item) for item in home_only[:4]],
        "other_only": [_phrase(item) for item in other_only[:4]],
        "actions": _actions(home_name, home_only, other_name, other_only, status),
        "opportunities": _opportunities(bool(shared), status),
    }


def _boundary(aligned: bool) -> str:
    return ("The bank's controls, implementation cost, penalties, and whether "
            "one jurisdiction's rule satisfies the other, are Not established. "
            "This is a difference in the indexed text, not a compliance gap.")


def _named(items: list[dict], text: str) -> str:
    if not items:
        return _topic(text)
    shown = sorted(items, key=_rank, reverse=True)
    return _join_items(shown[:2])


def _shared_lead(shared: list[dict], needed: bool) -> str:
    if not shared or not needed:
        return ""
    line = f"Both countries require {_join_items(shared[:1])}."
    forces = {item.get("force") for item in shared[:1]}
    if forces == {"explicit"}:
        line += " That wording is shall or must."
    elif forces == {"guidance"}:
        line += " That wording is should or expected to, which is guidance, not an explicit duty."
    return line


def _force_note(home_name: str, shared: list[dict], other_name: str,
                other_items: list[dict]) -> str:
    for item in shared:
        twin = next((o for o in other_items if _same(item["action"], o["action"])), None)
        if twin and item.get("force") != twin.get("force"):
            return (f"Human review: {home_name} writes the overlapping duty as "
                    f"{item.get('force', NE)}, and {other_name} writes it as "
                    f"{twin.get('force', NE)}. Whether guidance is enforced as "
                    "a rule is Not established.")
    return ""


def _matrix(home_name, home_text, other_name, other_text, home_regulator,
            other_regulator, home_published, other_published, home_ref,
            other_ref, other_known) -> list[dict]:
    other_side = other_text if other_known else None
    rows = [
        ("Issuing authority", home_regulator, other_regulator if other_known else ""),
        ("Jurisdiction", home_name, other_name if other_known else ""),
        ("Clause", home_ref, other_ref if other_known else ""),
        ("Legal status", "", ""),
        ("Page", "", ""),
        ("Regulated entities", _entities(home_text), _entities(other_side or "")),
        ("Publication date", home_published, other_published if other_known else ""),
        ("Effective date", "", ""),
        ("Compliance deadline", _when(home_text), _when(other_side or "")),
        ("Explicit obligation", _duty(home_text, "explicit"), _duty(other_side or "", "explicit")),
        ("Guidance", _duty(home_text, "guidance"), _duty(other_side or "", "guidance")),
    ]
    out = []
    for topic, home, other in rows:
        if topic in {"Legal status", "Page", "Effective date"}:
            out.append({"topic": topic, "home": NE, "other": NE if other_known else "Not assessed"})
            continue
        out.append({
            "topic": topic,
            "home": home or NE,
            "other": (other or NE) if other_known else "Not assessed",
        })
    return out


def _entities(text: str) -> str:
    found = []
    for pattern, label in _ENTITIES:
        if pattern.search(text) and label not in found:
            found.append(label)
    return ", ".join(found)


def _when(text: str) -> str:
    deadlines = extract_deadlines(text)
    if deadlines:
        return deadlines[0][0]
    cycles = extract_frequencies(text)
    return cycles[0] if cycles else ""


def _duty(text: str, force: str) -> str:
    items = [item for item in _obligations(text) if item.get("force") == force]
    if not items:
        return ""
    return _phrase(sorted(items, key=_rank, reverse=True)[0])


def _risk(home_text: str, other_text: str) -> list[str]:
    lines = []
    for label, pattern in _THEMES:
        home_hit = _snippet(pattern, home_text)
        other_hit = _snippet(pattern, other_text) if other_text else ""
        if home_hit or other_hit:
            parts = []
            if home_hit:
                parts.append(f"home text mentions {home_hit}")
            if other_hit:
                parts.append(f"other text mentions {other_hit}")
            lines.append(f"{label}: {'; '.join(parts)}.")
        else:
            lines.append(f"{label}: {NE}.")
    resilience = _snippet(_RESILIENCE, home_text) or (
        _snippet(_RESILIENCE, other_text) if other_text else "")
    lines.append("Operational resilience (continuity, recovery, tolerance, "
                 f"stress testing, incident management): {resilience or NE}.")
    lines.append("Required control named in the clause, beyond the obligation "
                 "itself: " + (_control(home_text, other_text) or NE) + ".")
    lines.append("Whether one shared control satisfies both jurisdictions: "
                 f"{NE}. A stricter clause does not satisfy the other.")
    lines.append("Compliance gap against the bank's own controls: "
                 f"{NE}. No evidence of those controls is in the index.")
    lines.append("Implementation cost, operational loss, capital effect, "
                 f"penalties and restrictions on business: {NE}.")
    return lines


def _control(home_text: str, other_text: str) -> str:
    pattern = re.compile(r"\b(?:internal controls?|control framework|policies and procedures)\b", re.I)
    return _snippet(pattern, home_text) or _snippet(pattern, other_text)


def _snippet(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text or "")
    if not match:
        return ""
    start = max(0, match.start() - 40)
    end = min(len(text), match.end() + 50)
    words = re.sub(r"\s+", " ", text[start:end]).strip(" ,.;")
    return words


def _actions(home_name, home_only, other_name, other_only, status) -> list[dict]:
    if status == "not_assessed":
        return [{"action": f"Index {other_name} text before comparing.",
                 "owner": NE, "priority": NE, "dependency": NE}]
    rows = []
    for country, items in ((home_name, home_only), (other_name, other_only)):
        for item in sorted(items, key=_rank, reverse=True)[:2]:
            kind = "explicit requirement" if item.get("force") == "explicit" else "guidance"
            owner = item["actor"] if item.get("actor") not in {"", "the bank"} else NE
            rows.append({
                "action": (f"Check the bank's own controls separately against "
                           f"{country}'s {kind}: {_phrase(item)}."),
                "owner": owner,
                "priority": NE,
                "dependency": NE,
            })
    if status == "unmatched" and not rows:
        rows.append({
            "action": f"Confirm whether {other_name} states this outside the matched set.",
            "owner": NE, "priority": NE, "dependency": NE,
        })
    if not rows:
        rows.append({
            "action": ("Where the wording overlaps, confirm each jurisdiction "
                       "on its own. Do not treat one clause as covering the other."),
            "owner": NE, "priority": NE, "dependency": NE,
        })
    return rows


def _opportunities(has_shared: bool, status: str) -> list[str]:
    if status in {"not_assessed", "unmatched"} or not has_shared:
        return ["A harmonized control is Not established for this pair. "
                "No cost saving is established."]
    return ["The overlapping obligation can be read once, then tested "
            "separately against each regulator. Overlap is not compliance "
            "with both, and no cost saving is established."]


def _side_sentence(country: str, items: list[dict], other: str, verb: str) -> str:
    if not items:
        return ""
    shown = sorted(items, key=_rank, reverse=True)[:2]
    lines = []
    for item in shown:
        if item.get("force") == "explicit":
            lines.append(f"{country} explicitly requires {_phrase(item)}")
        else:
            lines.append(
                f"{country} gives guidance (should or expected to): {_phrase(item)}")
    extra = "that obligation" if len(items) == 1 else "those obligations"
    return (f"{'. '.join(lines)}. {other} {verb} {extra} "
            "in the matched clause.")


def _timing(home_name: str, home_text: str, other_name: str,
            other_text: str) -> str:
    home_dead = extract_deadlines(home_text)
    other_dead = extract_deadlines(other_text)
    home_freq = extract_frequencies(home_text)
    other_freq = extract_frequencies(other_text)
    if home_dead and other_dead:
        h_label, h_hours = home_dead[0]
        o_label, o_hours = other_dead[0]
        if abs(h_hours - o_hours) < 1:
            return ""
        shorter = h_label if h_hours < o_hours else o_label
        return (f"{home_name} sets the time at {h_label}. {other_name} sets "
                f"the time at {o_label}. The shorter time is {shorter}.")
    if home_dead and not other_dead:
        return (f"{home_name} sets the time at {home_dead[0][0]}. "
                f"{other_name} states no time in the matched clause.")
    if other_dead and not home_dead:
        return (f"{other_name} sets the time at {other_dead[0][0]}. "
                f"{home_name} states no time in this clause.")
    if home_freq and not other_freq:
        return (f"{home_name} sets the review cycle at {home_freq[0]}. "
                f"{other_name} states no review cycle in the matched clause.")
    if other_freq and not home_freq:
        return (f"{other_name} sets the review cycle at {other_freq[0]}. "
                f"{home_name} states no review cycle in this clause.")
    if home_freq and other_freq and home_freq[0] != other_freq[0]:
        return (f"{home_name} sets the review cycle at {home_freq[0]}. "
                f"{other_name} sets it at {other_freq[0]}.")
    return ""


def _owner(home_name: str, home_items: list[dict], other_name: str,
           other_items: list[dict]) -> str:
    for item in home_items:
        twin = next((o for o in other_items if _same(item["action"], o["action"])), None)
        if twin is None:
            continue
        if not item["actor"] or not twin["actor"] or item["actor"] == twin["actor"]:
            continue
        if item["actor"] == "the bank" and twin["actor"] == "the bank":
            continue
        duty = re.sub(r"^to\s+", "", item["action"])
        return (f"The duty to {duty} sits with {item['actor']} in {home_name} "
                f"and with {twin['actor']} in {other_name}.")
    return ""


def _obligations(text: str) -> list[dict]:
    found: list[dict] = []
    plain = re.sub(r"\s+", " ", text).strip()
    for sentence in re.split(r"(?<=[.;])\s+", plain):
        for match in _MODAL.finditer(sentence):
            word = match.group(0).lower()
            force = "explicit" if word in _EXPLICIT else "guidance"
            item = _item(sentence[:match.start()], sentence[match.end():], text)
            for piece in (_split_and(item) if item else []):
                piece["force"] = force
                found.append(piece)
        for match in _ESTABLISH.finditer(sentence):
            action = _trim(match.group("object"), text)
            if len(_content(action)) >= 2:
                found.append({
                    "actor": "the bank",
                    "subject": "",
                    "action": "to establish " + _lower_first(action),
                    "force": "explicit",
                })
    return _dedupe(found)


def _item(before: str, after: str, source: str) -> dict | None:
    actor = _actor(before)
    subject = _subject(before, actor)
    action = _trim(after, source)
    if len(_content(action or subject)) < 2:
        return None
    if subject and len(_content(subject)) >= 2:
        actor = ""
    if actor:
        verb = action if action.lower().startswith("to ") else "to " + _lower_first(action)
        return {"actor": actor, "subject": "", "action": verb}
    if subject and action.lower().startswith("be "):
        subject = _lower_first(subject)
        if not re.match(r"^(?:the|a|an)\b", subject, re.I):
            subject = "the " + subject
        return {"actor": "", "subject": subject, "action": action}
    if action.lower().startswith("be ") or re.match(
            r"^(?:a|an|the|its|their|any|each|all|such|no|this|these|those)\b",
            action, re.I):
        return {"actor": "", "subject": "", "action": action}
    if action:
        return {"actor": "the bank", "subject": "",
                "action": "to " + _lower_first(action)}
    return None


def _actor(text: str) -> str:
    window = text[-90:]
    for pattern, label in _ACTORS:
        if pattern.search(window):
            return label
    return ""


def _subject(before: str, actor: str) -> str:
    cleaned = re.sub(r"^\d+[.)]\s*", "", before).strip(" ,;:-")
    cleaned = re.sub(
        r"^(?:and\s+)?(?:that\s+)?(?:furthermore\s*,?\s*)?", "", cleaned, flags=re.I)
    cleaned = re.sub(
        r"\b(banking corporations?|banks?|the institution|board of directors|"
        r"the board|board|senior management)\b",
        "", cleaned, flags=re.I)
    cleaned = re.sub(r"['’]s\b", "", cleaned)
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-'’")
    if actor and len(_content(cleaned)) < 2:
        return ""
    return cleaned


def _trim(text: str, source: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .;,")
    text = re.split(r"\b(?:alongside|in addition|hereinafter)\b", text, maxsplit=1,
                    flags=re.I)[0]
    text = re.split(
        r",\s*(?:and\s+)?(?:[A-Z][^,]{0,40}\s+)?(?:shall|must|should|is|are)\b",
        text, maxsplit=1)[0]
    text = re.sub(
        r"\b(?:for banking corporations|in these instructions|"
        r"under these instructions)\b.*",
        "", text, flags=re.I)
    text = text.strip(" .;,")
    if re.search(r"\bthis ratio\b", text, re.I) and re.search(r"liquidity", source, re.I):
        text = re.sub(r"\bthis ratio\b", "the liquidity ratio", text, flags=re.I)
    words = text.split()
    if len(words) > 16 and " and " in text:
        head = text.split(" and ", 1)[0]
        if len(head.split()) >= 4:
            text = head
            words = text.split()
    if len(words) > 16:
        text = " ".join(words[:16])
    # A cut must not stop on "including" or "and", which changes the duty.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(
            r"(?:[,;:]|\b(?:including|and|or|to|of|for|with|by|that)\b)\s*$",
            "", text, flags=re.I).strip(" .;,")
    return text


def _only(items: list[dict], others: list[dict]) -> list[dict]:
    kept = []
    for item in items:
        if any(_same(item["action"], other["action"]) for other in others):
            continue
        kept.append(item)
    return kept


def _same(a: str, b: str) -> bool:
    left, right = set(_content(a)), set(_content(b))
    if not left or not right:
        return False
    return len(left & right) / min(len(left), len(right)) >= 0.6


def _content(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP]


def _dedupe(items: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for item in items:
        if any(_same(item["action"], prev["action"]) for prev in kept):
            continue
        kept.append(item)
    return kept


def _rank(item: dict) -> int:
    action = item["action"].lower()
    if re.match(r"to be (?:used|subject|applied|calculated)\b", action):
        return 0
    if item["actor"] in {"the board", "senior management", "internal audit",
                         "the chief risk officer", "the compliance function",
                         "the compliance officer", "the risk management function"}:
        return 3
    if any(word in action for word in ("document", "notify", "approve", "report",
                                       "assess", "establish", "compliance")):
        return 2
    return 1


def _split_and(item: dict | None) -> list[dict]:
    """A second duty joined by 'and to report' is its own obligation."""
    if not item:
        return []
    action = item["action"]
    verbs = "|".join(sorted(_VERBS, key=len, reverse=True))
    match = re.search(rf"\s+and\s+(?:to\s+)?(?=(?:{verbs})\b)", action, flags=re.I)
    if not match:
        return [item]
    head, tail = action[:match.start()].strip(), action[match.end():].strip()
    if len(_content(head)) < 2 or len(_content(tail)) < 2:
        return [item]
    if not tail.lower().startswith("to "):
        tail = "to " + _lower_first(tail)
    second = dict(item)
    second["action"] = tail
    first = dict(item)
    first["action"] = head
    return [first, second]


def _join_items(items: list[dict]) -> str:
    if len(items) == 2 and items[0]["actor"] and items[0]["actor"] == items[1]["actor"]:
        return f"{items[0]['actor']} {items[0]['action']} and {items[1]['action']}"
    return _join(_phrase(item) for item in items)


def _phrase(item: dict) -> str:
    if item["actor"]:
        return f"{item['actor']} {item['action']}"
    if item["subject"]:
        return f"that {item['subject']} {item['action']}"
    return item["action"]


def _join(parts) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} and {parts[1]}"


def _topic(text: str) -> str:
    plain = re.sub(r"\s+", " ", text).strip()
    # "2. Risk weighted assets" must keep the words after the clause number.
    plain = re.sub(r"^(?:article\s*\([^)]*\)\s*:?\s*)?\d+[.)]\s*", "",
                   plain, flags=re.I).strip()
    sentence = re.split(r"(?<=[.])\s+", plain)[0] if plain else ""
    words = sentence.split()
    if len(words) > 18:
        sentence = " ".join(words[:18]).rstrip(".,;") + "…"
    return sentence or "the selected clause"


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text
