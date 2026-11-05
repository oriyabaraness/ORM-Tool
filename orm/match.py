"""Find the equivalent clause in other countries.

For every tagged clause, look at clauses in the *other* jurisdictions that
carry the same risk category and rank them by

    0.7 x text similarity (TF-IDF cosine over the whole corpus)
  + 0.3 x overlap of baseline expectations both clauses satisfy

Each match keeps the reasons it was made (shared expectations, shared key
terms) so the UI can show *why* two clauses were paired.

Pure Python on purpose: no extra dependencies, and the corpus for a handful of
regulators is small enough that this runs in seconds.
"""
from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter, defaultdict

STOPWORDS = set("""
a about above after again all also an and any are as at be been before being
below between both but by can could did do does each either for from further
had has have having he her here hers him his how if in into is it its itself
may might more most must no nor not of off on once only or other our out over
own same shall she should so some such than that the their them then there
these they this those through to under until up upon very was we were what
when where which while who whom why will with within without would you your
bank banks banking corporation corporations licensed institution institutions
directive directives instruction instructions regulation regulations article
section paragraph clause chapter part provided provision provisions accordance
pursuant herein thereof therein hereby including include includes per etc
said following above below shall must may made make set referred subject
""".split())

_WORD = re.compile(r"[a-z][a-z\-]{2,}")


def _stem(word: str) -> str:
    for suffix in ("ations", "ation", "ments", "ment", "ings", "ing", "ies",
                   "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


class Vectorizer:
    """TF-IDF with sublinear tf and L2-normalized vectors."""

    def __init__(self, texts: list[str]):
        self.n = len(texts)
        df: Counter = Counter()
        self._tokens = [tokens(t) for t in texts]
        for toks in self._tokens:
            df.update(set(toks))
        self.idf = {t: math.log((1 + self.n) / (1 + d)) + 1 for t, d in df.items()}

    def vector(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        vec = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def vectors(self) -> list[dict[str, float]]:
        return [self.vector(t) for t in self._tokens]


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def shared_terms(a: dict[str, float], b: dict[str, float], k: int = 5) -> list[str]:
    common = [(a[t] * b[t], t) for t in a.keys() & b.keys()]
    return [t for _, t in sorted(common, reverse=True)[:k]]


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


TEXT_WEIGHT, EXPECTATION_WEIGHT = 0.7, 0.3
MIN_SCORE = 0.06


def compute_matches(conn: sqlite3.Connection, top_n: int = 5) -> int:
    """Rebuild provision_match for every category. Returns rows written."""
    conn.execute("DELETE FROM provision_match")
    rows = conn.execute("""
        SELECT p.id, p.text, d.jurisdiction FROM provision p
        JOIN document d ON d.id = p.document_id
    """).fetchall()
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    vec = Vectorizer([r["text"] for r in rows])
    vectors = dict(zip(ids, vec.vectors()))
    jurisdiction = {r["id"]: r["jurisdiction"] for r in rows}

    expectations: dict[int, set[str]] = defaultdict(set)
    for r in conn.execute("SELECT provision_id, expectation_id FROM expectation_hit"):
        expectations[r["provision_id"]].add(r["expectation_id"])

    by_category: dict[str, list[int]] = defaultdict(list)
    for r in conn.execute("SELECT provision_id, category_id FROM provision_category "
                          "WHERE reviewed >= 0"):
        by_category[r["category_id"]].append(r["provision_id"])

    written = 0
    for category_id, pids in by_category.items():
        by_j: dict[str, list[int]] = defaultdict(list)
        for pid in pids:
            by_j[jurisdiction[pid]].append(pid)
        if len(by_j) < 2:
            continue
        for j, own in by_j.items():
            others = [p for oj, ps in by_j.items() if oj != j for p in ps]
            for pid in own:
                va, ea = vectors[pid], expectations.get(pid, set())
                scored = []
                for other in others:
                    cos = cosine(va, vectors[other])
                    eb = expectations.get(other, set())
                    score = TEXT_WEIGHT * cos + EXPECTATION_WEIGHT * jaccard(ea, eb)
                    if score >= MIN_SCORE:
                        scored.append((score, cos, other, ea & eb))
                scored.sort(key=lambda s: -s[0])
                for score, cos, other, common in scored[:top_n]:
                    conn.execute(
                        "INSERT INTO provision_match(provision_id, category_id, "
                        "match_id, score, text_similarity, shared_expectations, "
                        "shared_terms) VALUES (?,?,?,?,?,?,?)",
                        (pid, category_id, other, round(score, 4), round(cos, 4),
                         ",".join(sorted(common)),
                         ", ".join(shared_terms(va, vectors[other]))))
                    written += 1
    return written


def strength(score: float) -> str:
    if score >= 0.35:
        return "Strong match"
    if score >= 0.18:
        return "Partial match"
    return "Weak match"
