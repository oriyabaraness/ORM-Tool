"""Regulatory Delta Language (RDL): the fixed vocabulary of the ORM Analysis
Standard, in one place.

Everything an analyst "signs up to" lives here, so the rest of the engine
reads it instead of hard-coding it:

  Layer 1  AUTHORITY      who writes the rules for each country and category
  Layer 2  FORCE, ACTIONS, OBJECTS, ...   the obligation grammar's allowed values
  Layer 3  LENSES          Basel loss event + resilience principle per category
  Layer 4  VERDICTS        the six directional verdicts and their precedence
  Layer 5  RII_WEIGHTS     score weights (the part to keep confidential once tuned)

Changing a term or a weight is a change to the standard: bump VERSION and add
a line to CHANGELOG.
"""
from __future__ import annotations

from dataclasses import dataclass

VERSION = "RDL v1.0"
CHANGELOG = (
    ("RDL v1.0", "2026-11-05",
     "First coded version. Frequency adds Weekly and Semi-annually; Evidence "
     "adds Written record, so common clauses can be coded without forcing them. "
     "For matching, notify and report count as one action family (inform), "
     "since regulators use both verbs for the same duty."),
)

# --- Layer 1: authority map ----------------------------------------------------

IN_SCOPE, OTHER, SHARED = "in_scope", "other_authority", "shared"
SCOPE_LABELS = {IN_SCOPE: "In scope", OTHER: "Other authority", SHARED: "Shared"}


@dataclass(frozen=True)
class Authority:
    scope: str
    authority: str          # who writes the rules in this area


# The regulator the tool indexes for each country, and the areas where someone
# else writes the rules. Anything not listed is IN_SCOPE for the indexed one.
INDEXED_REGULATOR = {
    "IL": "Bank of Israel",
    "JO": "Central Bank of Jordan",
    "TR": "CBRT",
}
_BDDK = "BRSA (BDDK)"
AUTHORITY_EXCEPTIONS: dict[tuple[str, str], Authority] = {
    # Turkey: the central bank writes payments and monetary rules; banking
    # prudential and operational rules come from the BRSA, AML from MASAK.
    **{("TR", c): Authority(OTHER, _BDDK) for c in (
        "governance", "op_resilience", "third_party", "ict_cyber",
        "incident_reporting", "credit", "capital_liquidity", "market",
        "climate", "licensing")},
    ("TR", "aml"): Authority(OTHER, "MASAK (financial crimes board)"),
    ("TR", "conduct"): Authority(SHARED, f"CBRT and {_BDDK}"),
}


def authority(jurisdiction: str, category_id: str) -> Authority:
    """Layer 1: who is responsible for this area in this country."""
    found = AUTHORITY_EXCEPTIONS.get((jurisdiction, category_id))
    if found:
        return found
    return Authority(IN_SCOPE, INDEXED_REGULATOR.get(jurisdiction, ""))


# --- Layer 2: obligation grammar -----------------------------------------------

FORCES = ("MUST", "MUST-OR-EXPLAIN", "SHOULD", "MAY", "MUST-NOT")
# How binding each force is (Bindingness in the Intensity Index, and the first
# test in a directional verdict). A prohibition binds as hard as a MUST.
FORCE_WEIGHT = {"MUST": 1.0, "MUST-NOT": 1.0, "MUST-OR-EXPLAIN": 0.8,
                "SHOULD": 0.5, "MAY": 0.2}

ADDRESSEES = ("Board", "Senior management", "Named function", "Institution",
              "Third party")
ACTIONS = ("establish", "approve", "document", "test", "monitor", "report",
           "notify", "review", "retain", "restrict")
OBJECTS = ("policy", "plan", "register", "limit", "system", "incident", "data",
           "contract", "customer")
TRIGGERS = ("On an event", "Before an action", "On a schedule", "Always")
FREQUENCIES = ("Continuous", "Per event", "Weekly", "Monthly", "Quarterly",
               "Semi-annually", "Annually", "Every N years")
EVIDENCE = ("Minutes", "Report", "Test result", "Register entry", "Attestation",
            "Written record")
PROPORTIONALITY = ("All institutions", "By size", "By risk profile",
                   "By licence type")

# Verbs regulators use interchangeably for one duty; records align on family.
ACTION_FAMILY = {"notify": "inform", "report": "inform"}


def action_family(action: str | None) -> str | None:
    return ACTION_FAMILY.get(action, action) if action else None


# --- Layer 3: risk lenses ------------------------------------------------------

BASEL_EVENT_TYPES = (
    "Internal fraud",
    "External fraud",
    "Employment practices and workplace safety",
    "Clients, products and business practices",
    "Damage to physical assets",
    "Business disruption and system failures",
    "Execution, delivery and process management",
)
RESILIENCE_PRINCIPLES = (
    "Governance",
    "Operational risk management",
    "Business continuity planning and testing",
    "Mapping of interconnections and interdependencies",
    "Third-party dependency management",
    "Incident management",
    "Resilient ICT, including cyber security",
)


@dataclass(frozen=True)
class Lens:
    loss_events: tuple[str, ...]
    principles: tuple[str, ...]


LENSES: dict[str, Lens] = {
    "governance": Lens(BASEL_EVENT_TYPES, ("Governance",)),
    "op_resilience": Lens(("Business disruption and system failures",),
                          ("Business continuity planning and testing",
                           "Mapping of interconnections and interdependencies")),
    "third_party": Lens(("Execution, delivery and process management",),
                        ("Third-party dependency management",)),
    "ict_cyber": Lens(("External fraud", "Business disruption and system failures"),
                      ("Resilient ICT, including cyber security",)),
    "incident_reporting": Lens(("Business disruption and system failures",),
                               ("Incident management",)),
    "aml": Lens(("Clients, products and business practices", "External fraud"), ()),
    "conduct": Lens(("Clients, products and business practices",), ()),
    "payments": Lens(("Execution, delivery and process management",),
                     ("Mapping of interconnections and interdependencies",)),
}
CONTROL_TYPES = ("Preventive", "Detective", "Corrective", "Governance")


def lens(category_id: str) -> Lens | None:
    """Layer 3 lenses for a category; None = not operational risk (scored
    separately so it never dilutes an ORM score)."""
    return LENSES.get(category_id)


# --- Layer 4: directional verdicts ---------------------------------------------

EQUIVALENT = "Equivalent"
STRICTER = "Stricter"
LOOSER = "Looser"
DIFFERENT = "Different mechanism"
GAP = "Gap"
NOT_ASSESSED = "Not assessed"
VERDICTS = (EQUIVALENT, STRICTER, LOOSER, DIFFERENT, GAP, NOT_ASSESSED)
VERDICT_MEANING = {
    EQUIVALENT: "Your home control already satisfies this",
    STRICTER: "You must upgrade the control to enter",
    LOOSER: "Your control over-complies; no change needed",
    DIFFERENT: "You need a new control, not a tweak",
    GAP: "Target sets no rule; your own policy decides",
    NOT_ASSESSED: "Unknown; do not rely on it",
}
# The first part that differs decides, in this order.
PRECEDENCE = ("force", "proportionality", "measure", "frequency", "evidence")
MEASURE_TOLERANCE = 0.10      # "Measure within 10%" counts as the same


def invert(verdict: str) -> str:
    """The same pair read the other way round (target becomes home)."""
    return {STRICTER: LOOSER, LOOSER: STRICTER}.get(verdict, verdict)


# --- Layer 5: scores -----------------------------------------------------------

RII_WEIGHTS = {"coverage": 0.35, "bindingness": 0.25, "specificity": 0.20,
               "recency": 0.10, "enforcement": 0.10}
RECENCY_FULL_YEARS, RECENCY_ZERO_YEARS = 2, 10
GRADE_A_SHARE = 0.8    # share of clauses a specialist confirmed for grade A
GRADE_MEANING = {
    "A": "Full text, specialist-reviewed",
    "B": "Full text, machine only",
    "C": "Titles and metadata only",
}
