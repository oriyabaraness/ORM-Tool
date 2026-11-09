"""Turn regulation clauses into structured obligations, and suggest the
control that answers each one.

An obligation is one sentence of a clause that imposes a duty ("shall",
"must", "is required to", or the softer "should"). For each one we record:

    who       the actor named before the modal verb (the board, the bank ...)
    what      the duty, as written after the modal verb
    deadline  "within 24 hours" etc., normalized to hours
    frequency "annually", "at least once a year" ...
    evidence  what an auditor would ask to see (a hint from the verbs used)
    source    the exact sentence and clause it came from

Two extractors fill the same record:

  rule  -- pattern-based, always available, transparent (the default)
  llm   -- Claude reads a whole directive (orm/llm.py). Its results are cached
           as JSON under orm_texts/llm/<document id>.json and committed, so a
           deploy uses them without an API key. Where a cache exists it
           replaces the rule-based obligations for that document.

Every obligation gets a stable `okey` (hash of document + sentence), so human
review decisions kept in the state store (orm/state.py) survive rebuilds of
the index. A changed sentence gets a new key: its old review no longer
applies, which is what an auditor would expect.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import defaultdict

from . import controls as control_lib
from . import match, review
from .classify import extract_deadlines, extract_frequencies

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLM_CACHE_DIR = os.path.join(HERE, "orm_texts", "llm")

SCHEMA = """
CREATE TABLE IF NOT EXISTS obligation (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    okey           TEXT NOT NULL,
    provision_id   INTEGER NOT NULL REFERENCES provision(id) ON DELETE CASCADE,
    document_id    TEXT NOT NULL,
    jurisdiction   TEXT NOT NULL,
    category_id    TEXT NOT NULL,
    actor          TEXT,
    action         TEXT NOT NULL,
    modality       TEXT NOT NULL,      -- mandatory | expected
    deadline_text  TEXT,
    deadline_hours REAL,
    frequency      TEXT,
    evidence       TEXT,
    sentence       TEXT NOT NULL,
    method         TEXT NOT NULL       -- rule | llm
);
CREATE TABLE IF NOT EXISTS obligation_control (
    obligation_id  INTEGER NOT NULL REFERENCES obligation(id) ON DELETE CASCADE,
    control_id     TEXT NOT NULL,
    score          REAL NOT NULL,
    reason         TEXT,
    PRIMARY KEY (obligation_id, control_id)
);
CREATE INDEX IF NOT EXISTS ix_obl_scope ON obligation(jurisdiction, category_id);
CREATE INDEX IF NOT EXISTS ix_obl_doc ON obligation(document_id);
CREATE INDEX IF NOT EXISTS ix_obl_key ON obligation(okey);
"""

_MODAL = re.compile(
    r"\b(?P<m>shall|must|is required to|are required to|is obliged to|"
    r"are obliged to|is obligated to|are obligated to|should|is expected to|"
    r"are expected to)\b", re.I)
_MANDATORY = {"shall", "must", "is required to", "are required to",
              "is obliged to", "are obliged to", "is obligated to", "are obligated to"}
# "shall mean", "shall apply", "shall enter into force" ... define or scope,
# they do not ask anyone to do anything.
_NOT_A_DUTY = re.compile(
    r"^\s*(?:not apply|not be applicable|mean|means|include|be deemed|be construed|be interpreted|apply|"
    r"enter into (?:force|effect)|come into (?:force|effect)|take effect|"
    r"be effective|remain in (?:force|effect)|have the (?:same )?meaning|"
    r"be referred to|refer to|be cited)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'0-9])")

# verb -> what an auditor would ask to see
_EVIDENCE = (
    (r"\bapprov", "Board or committee minutes recording the approval"),
    (r"\b(?:notif|report|submit|inform|send|deliver)", "Copy of the report or notification, with the date it was sent"),
    (r"\b(?:test|drill|exercis|simulat)", "Test plan and results report"),
    (r"\b(?:review|re-?assess|evaluat|update)", "Dated review record with conclusions and follow-up"),
    (r"\b(?:appoint|designat|nominat)", "Appointment letter or organisation chart"),
    (r"\b(?:train|educat)", "Training materials and attendance records"),
    (r"\b(?:monitor|track|supervis|oversee)", "Monitoring reports or dashboards"),
    (r"\b(?:maintain|keep|record|retain|register|inventor|log)", "Extract from the register or records"),
    (r"\b(?:document|written|polic|procedur|plan|framework|set out|define|establish|adopt)",
     "Approved, version-controlled policy, procedure or plan"),
    (r"\b(?:assess|analy[sz]|identif|measur|calculat)", "Assessment or analysis report"),
    (r"\b(?:disclos|publish|provide (?:the )?customer)", "The disclosure as published or sent to customers"),
)
_EVIDENCE = tuple((re.compile(p, re.I), label) for p, label in _EVIDENCE)
_DEFAULT_EVIDENCE = "Evidence that the requirement is carried out"


def okey(document_id: str, sentence: str) -> str:
    norm = re.sub(r"\W+", " ", sentence.lower()).strip()
    return hashlib.sha1(f"{document_id}|{norm}".encode("utf-8")).hexdigest()[:16]


def evidence_hint(text: str) -> str:
    for pattern, label in _EVIDENCE:
        if pattern.search(text):
            return label
    return _DEFAULT_EVIDENCE


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    return text[:1].upper() + text[1:] if text else text


def _cut(text: str, n: int = 280) -> str:
    text = _clean(text)
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + " …"


def _who(before: str) -> str:
    """The actor (the board, the bank ...) or, failing that, the thing the
    sentence is about ("the business continuity plan")."""
    actor = review._actor(before)
    if actor:
        return actor
    tail = re.sub(r"^.*?(?:[,;:]|\b(?:and|that|which|where|when)\b)\s*", "",
                  before.strip()[-120:], flags=re.I) if re.search(
        r"[,;:]|\b(?:and|that|which|where|when)\b", before.strip()[-120:], re.I) \
        else before.strip()[-120:]
    tail = re.sub(r"^\(?[\dA-Za-z]{1,4}[.)]\s*", "", tail).strip(" ,;:-")
    words = tail.split()
    return " ".join(words[-8:]) if 1 <= len(words) <= 14 else ""


def extract(text: str) -> list[dict]:
    """Rule-based obligations from one clause's text (no database needed)."""
    plain = re.sub(r"\s+", " ", text or "").strip()
    out, seen = [], set()
    for sentence in _SENTENCE.split(plain):
        sentence = sentence.strip()
        if not 30 <= len(sentence) <= 1200:
            continue
        m = _MODAL.search(sentence)
        if not m:
            continue
        after = sentence[m.end():]
        words = re.findall(r"[A-Za-z]{2,}", after)
        lead_in = after.rstrip().endswith((":", "following")) and len(words) <= 6
        if _NOT_A_DUTY.match(after) or len(words) < 3 or lead_in:
            continue
        before = sentence[:m.start()]
        modal = m.group("m").lower()
        deadlines = extract_deadlines(sentence)
        freqs = extract_frequencies(sentence)
        action = _cut(after)
        key = action.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "actor": _who(before),
            "action": action,
            "modality": "mandatory" if modal in _MANDATORY else "expected",
            "deadline_text": deadlines[0][0] if deadlines else "",
            "deadline_hours": deadlines[0][1] if deadlines else None,
            "frequency": ", ".join(freqs),
            "evidence": evidence_hint(after),
            "sentence": _cut(sentence, 1200),
        })
    return out


# --- LLM cache ------------------------------------------------------------------

def llm_cache_path(document_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", document_id)
    return os.path.join(LLM_CACHE_DIR, safe + ".json")


def load_llm_cache(document_id: str) -> dict[int, list[dict]] | None:
    """{provision seq: [obligation, ...]} if Claude has read this document."""
    path = llm_cache_path(document_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out: dict[int, list[dict]] = defaultdict(list)
    for item in data.get("obligations", []):
        if not item.get("action") or not item.get("sentence"):
            continue
        out[int(item.get("seq", -1))].append(item)
    return out


# --- build -----------------------------------------------------------------------

def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def build_all(conn: sqlite3.Connection) -> dict[str, int]:
    """(Re)build every obligation and its suggested control. Reviews live in
    the state store, keyed by okey, so nothing human is lost here."""
    init(conn)
    conn.execute("DELETE FROM obligation_control")
    conn.execute("DELETE FROM obligation")
    # primary category per provision = its best-scoring tag
    rows = conn.execute("""
        SELECT p.id, p.seq, p.text, p.document_id, d.jurisdiction,
               (SELECT pc.category_id FROM provision_category pc
                 WHERE pc.provision_id = p.id AND pc.reviewed >= 0
                 ORDER BY pc.reviewed DESC, pc.score DESC LIMIT 1) AS category_id
        FROM provision p JOIN document d ON d.id = p.document_id
        ORDER BY p.document_id, p.seq
    """).fetchall()
    llm_by_doc: dict[str, dict | None] = {}
    n_rule = n_llm = 0
    for r in rows:
        if not r["category_id"]:
            continue
        doc = r["document_id"]
        if doc not in llm_by_doc:
            llm_by_doc[doc] = load_llm_cache(doc)
        cached = llm_by_doc[doc]
        if cached is not None:
            items, method = cached.get(r["seq"], []), "llm"
        else:
            items, method = extract(r["text"]), "rule"
        for it in items:
            hours = it.get("deadline_hours")
            conn.execute(
                "INSERT INTO obligation(okey, provision_id, document_id, jurisdiction, "
                "category_id, actor, action, modality, deadline_text, deadline_hours, "
                "frequency, evidence, sentence, method) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (okey(doc, it["sentence"]), r["id"], doc, r["jurisdiction"],
                 r["category_id"], it.get("actor", ""), it["action"],
                 it.get("modality", "mandatory"), it.get("deadline_text", ""),
                 float(hours) if hours not in (None, "") else None,
                 it.get("frequency", ""),
                 it.get("evidence") or evidence_hint(it["action"]),
                 it["sentence"], method))
            if method == "llm":
                n_llm += 1
            else:
                n_rule += 1
    n_map = map_controls(conn)
    return {"obligations": n_rule + n_llm, "from_llm": n_llm,
            "control_suggestions": n_map}


# --- control suggestions ----------------------------------------------------------

MIN_CONTROL_SCORE = 0.17


def _control_text(c: control_lib.Control) -> str:
    return f"{c.name}. {c.description} {c.evidence}"


def score_control(c: control_lib.Control, text: str, vec, cvec) -> tuple[float, list[str]]:
    hits = [k for k in c.keywords if re.search(k, text, re.I)]
    kw = len(hits) / max(1, len(c.keywords))
    cos = match.cosine(vec, cvec)
    return 0.6 * kw + 0.4 * cos, hits


OTHER_CATEGORY_WEIGHT = 0.75


def map_controls(conn: sqlite3.Connection, top_n: int = 2) -> int:
    """Suggest up to `top_n` library controls per obligation. Controls in a
    category the clause is tagged with score in full; controls from other
    categories are discounted, so a notification duty inside a continuity
    directive can still find the incident-notification control."""
    rows = conn.execute("""
        SELECT o.id, o.category_id, o.action, o.sentence,
               (SELECT GROUP_CONCAT(pc.category_id) FROM provision_category pc
                 WHERE pc.provision_id = o.provision_id AND pc.reviewed >= 0) AS tags
        FROM obligation o""").fetchall()
    if not rows:
        return 0
    texts = [f"{r['action']} {r['sentence']}" for r in rows]
    lib = list(control_lib.LIBRARY)
    vec = match.Vectorizer(texts + [_control_text(c) for c in lib])
    ovecs = [vec.vector(match.tokens(t)) for t in texts]
    cvecs = {c.id: vec.vector(match.tokens(_control_text(c))) for c in lib}
    written = 0
    for r, text, ov in zip(rows, texts, ovecs):
        scored = []
        tags = set((r["tags"] or r["category_id"]).split(","))
        for c in lib:
            score, hits = score_control(c, text, ov, cvecs[c.id])
            if c.category_id not in tags:
                score *= OTHER_CATEGORY_WEIGHT
            if score >= MIN_CONTROL_SCORE:
                scored.append((score, c, hits))
        scored.sort(key=lambda s: -s[0])
        for score, c, hits in scored[:top_n]:
            reason = ("keywords: " + ", ".join(h.strip("\\b") for h in hits)) if hits \
                else "similar wording"
            conn.execute(
                "INSERT INTO obligation_control(obligation_id, control_id, score, reason) "
                "VALUES (?,?,?,?)", (r["id"], c.id, round(score, 4), reason))
            written += 1
    return written
