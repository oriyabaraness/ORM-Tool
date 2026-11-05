"""Risk taxonomy used to line up regulation across jurisdictions.

Every document and provision is mapped to one or more of these categories.
The structure follows the themes supervisors actually write rules about,
with the operational-risk-management (ORM) core flagged separately from
prudential topics so the comparison can be narrowed to ORM.

Keyword rules are deliberately transparent (regex fragments, English source
text plus the Hebrew subject labels BOI uses in its directive index). They are
a first-pass classifier: every hit keeps its evidence so a reviewer can
confirm or reject it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Expectation:
    """A baseline element a mature framework is expected to contain.

    Used for gap analysis: if no provision in a jurisdiction matches any of
    the patterns, the element is reported as "not found" for that country.
    """

    id: str
    label: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    description: str
    orm_core: bool
    keywords: tuple[str, ...]
    he_subjects: tuple[str, ...] = ()
    expectations: tuple[Expectation, ...] = field(default_factory=tuple)


CATEGORIES: tuple[Category, ...] = (
    Category(
        id="governance",
        name="Governance & risk framework",
        description="Board and management responsibilities, risk management "
                    "function, compliance, internal audit and internal control.",
        orm_core=True,
        keywords=(
            r"board of directors", r"corporate governance", r"governance",
            r"risk management", r"chief risk officer", r"compliance",
            r"internal audit", r"internal control", r"compensation polic",
            r"retention of documents", r"business controls",
            r"risk appetite", r"three lines", r"auditor",
        ),
        he_subjects=("ממשל תאגידי", "ניהול סיכונים", "ניהול ובקרה",
                     "שליטה והחזקה", "רואה החשבון המבקר"),
        expectations=(
            Expectation("gov_board", "Board holds ultimate responsibility for risk",
                        (r"board of directors (shall|is responsible|must|will) "
                         r"[^.]{0,80}(risk|approve)",
                         r"responsibilit\w+ of the board")),
            Expectation("gov_cro", "Independent risk management function / CRO",
                        (r"chief risk officer", r"risk management function",
                         r"independent risk")),
            Expectation("gov_appetite", "Documented risk appetite",
                        (r"risk appetite",)),
            Expectation("gov_compliance", "Compliance function",
                        (r"compliance (function|officer)",)),
            Expectation("gov_audit", "Internal audit coverage",
                        (r"internal audit",)),
        ),
    ),
    Category(
        id="op_resilience",
        name="Operational risk & resilience",
        description="Operational risk management, business continuity, "
                    "disaster recovery and operational resilience.",
        orm_core=True,
        keywords=(
            r"operational risk", r"business continuity", r"disaster recovery",
            r"resilien\w+", r"continuity plan", r"recovery time",
            r"crisis management", r"emergency", r"\(temporary directive\)",
        ),
        he_subjects=("סיכון תפעולי",),
        expectations=(
            Expectation("res_bcp", "Documented business continuity plan",
                        (r"business continuity plan", r"continuity plan",
                         r"\bBCP\b")),
            Expectation("res_rto", "Recovery time / recovery point objectives",
                        (r"recovery time", r"recovery point", r"\bRTO\b",
                         r"\bRPO\b")),
            Expectation("res_test", "Periodic testing of continuity arrangements",
                        (r"test\w*[^.]{0,80}(continuity|recovery|backup|drill)",
                         r"(continuity|recovery|drill)[^.]{0,80}test\w*")),
            Expectation("res_scenario", "Severe but plausible scenarios",
                        (r"scenario", r"severe but plausible")),
            Expectation("res_loss_data", "Operational loss data collection",
                        (r"loss data", r"loss event", r"database of (operational )?"
                         r"(loss|event)")),
        ),
    ),
    Category(
        id="third_party",
        name="Outsourcing & third-party",
        description="Outsourcing, cloud and other third-party service "
                    "providers, including notification and exit.",
        orm_core=True,
        keywords=(
            r"outsourc\w+", r"third[- ]part\w+", r"service provider",
            r"cloud", r"supplier", r"vendor",
        ),
        he_subjects=("מיקור חוץ",),
        expectations=(
            Expectation("tp_due_diligence", "Due diligence before engagement",
                        (r"due diligence",)),
            Expectation("tp_contract", "Contract terms incl. audit / access rights",
                        (r"(right|rights) of (audit|access)",
                         r"(audit|access) rights",
                         r"contract[^.]{0,80}(audit|access|inspect)")),
            Expectation("tp_notify", "Supervisor notification / approval",
                        (r"(notify|notification|approval|report)[^.]{0,80}"
                         r"(supervisor|central bank|banking supervision)",)),
            Expectation("tp_exit", "Exit strategy / termination plan",
                        (r"exit (strategy|plan)", r"terminat\w+[^.]{0,60}"
                         r"(plan|transition)")),
            Expectation("tp_concentration", "Concentration risk of providers",
                        (r"concentration[^.]{0,60}(provider|supplier|vendor|"
                         r"outsourc)",)),
        ),
    ),
    Category(
        id="ict_cyber",
        name="IT, cyber & information security",
        description="Information technology risk, information security, "
                    "cyber defense and electronic banking channels.",
        orm_core=True,
        keywords=(
            r"cyber", r"information security", r"information technology",
            r"electronic means", r"encryption", r"penetration test",
            r"technolog\w+ risk", r"data protection",
        ),
        he_subjects=("סיכוני טכנולוגיית המידע, אבטחת מידע והגנת סייבר",),
        expectations=(
            Expectation("cy_ciso", "Designated information-security / cyber officer",
                        (r"chief (information )?security officer", r"\bCISO\b",
                         r"cyber (defense|security) (officer|manager)")),
            Expectation("cy_pentest", "Penetration / security testing",
                        (r"penetration test", r"vulnerability (scan|assess)",
                         r"red team")),
            Expectation("cy_ir", "Cyber incident response plan",
                        (r"incident response", r"response plan")),
            Expectation("cy_access", "Access control and encryption",
                        (r"access control", r"encrypt\w*",
                         r"multi[- ]factor|two[- ]factor")),
        ),
    ),
    Category(
        id="incident_reporting",
        name="Incident & event reporting",
        description="Obligations to notify the supervisor of incidents, "
                    "failures and material events, and their timelines.",
        orm_core=True,
        keywords=(
            r"report\w*[^.]{0,40}(incident|event|failure|breach)",
            r"(incident|event|failure|breach)[^.]{0,40}report\w*",
            r"notify the (supervisor|central bank|banking supervision)",
            r"immediate(ly)? report",
        ),
        expectations=(
            Expectation("ir_notify", "Duty to notify the supervisor",
                        (r"(notify|inform|report to) the (supervisor|central bank|"
                         r"banking supervision|supervisor of banks)",)),
            Expectation("ir_timeline", "Defined reporting timeline",
                        (r"within\s+\S+\s+(business |working )?(hours?|days?)"
                         r"[^.]{0,80}(report|notif)",
                         r"(report|notif)\w*[^.]{0,80}within\s+\S+\s+"
                         r"(business |working )?(hours?|days?)")),
            Expectation("ir_rca", "Root-cause analysis / post-incident review",
                        (r"root cause", r"lessons learned",
                         r"post[- ]incident")),
        ),
    ),
    Category(
        id="aml",
        name="AML/CFT & sanctions",
        description="Anti-money laundering, terror financing, suspicious "
                    "activity reporting, customer due diligence and sanctions.",
        orm_core=True,
        keywords=(
            r"money laundering", r"terror\w* financing", r"suspicious",
            r"know your customer", r"\bKYC\b", r"customer due diligence",
            r"sanction", r"\bAML\b", r"politically exposed",
        ),
        he_subjects=("איסור הלבנת הון",),
        expectations=(
            Expectation("aml_cdd", "Customer due diligence / KYC",
                        (r"customer due diligence", r"know your customer",
                         r"\bKYC\b", r"identif\w+ (of )?(the )?customer")),
            Expectation("aml_str", "Suspicious activity reporting",
                        (r"suspicious (activity|transaction)",)),
            Expectation("aml_pep", "Politically exposed persons",
                        (r"politically exposed", r"\bPEPs?\b")),
            Expectation("aml_records", "Record keeping period",
                        (r"(retain|keep|maintain)[^.]{0,60}(records|documents)"
                         r"[^.]{0,60}(years?)",)),
        ),
    ),
    Category(
        id="conduct",
        name="Conduct & consumer protection",
        description="Fair treatment, disclosure, fees, complaints, advertising "
                    "and access to basic banking.",
        orm_core=True,
        keywords=(
            r"consumer", r"complaint", r"disclos\w+ to (the )?customer",
            r"fees?\b", r"commission", r"advertis\w+", r"fair treatment",
            r"disabilit\w+", r"basic bank account", r"customer",
            r"debt collection", r"minors'? accounts?",
            r"erroneous entry", r"new immigrants", r"legal fees",
        ),
        he_subjects=("עמלות", "חשבונות בנק", "חשבונות ללא תנועה",
                     "שיקים ללא כיסוי", "פתיחת סניפים והצבת ATM"),
        expectations=(
            Expectation("con_complaints", "Complaints handling procedure",
                        (r"complaint",)),
            Expectation("con_disclosure", "Pre-contract disclosure to customers",
                        (r"disclos\w+[^.]{0,60}customer",
                         r"customer[^.]{0,60}disclos\w+")),
            Expectation("con_fees", "Fee transparency",
                        (r"(fee|commission)[^.]{0,60}(disclos|publish|tariff|"
                         r"price list)",)),
            Expectation("con_vulnerable", "Vulnerable customers / accessibility",
                        (r"disabilit\w+", r"vulnerable", r"elderly",
                         r"accessib\w+")),
        ),
    ),
    Category(
        id="payments",
        name="Payments & fintech",
        description="Payment services, transfers, cards, cheques, ATMs, "
                    "open banking and fintech sandboxes.",
        orm_core=False,
        keywords=(
            r"payment", r"transfer of funds", r"credit card", r"debit card",
            r"\bATMs?\b", r"cheque|check(book)?s?\b", r"open banking",
            r"fintech", r"sandbox", r"e-?money", r"electronic payment",
        ),
        he_subjects=("אמצעי תשלום",),
    ),
    Category(
        id="credit",
        name="Credit risk",
        description="Credit risk management, impairment, collateral, "
                    "concentration and related-party exposures.",
        orm_core=False,
        keywords=(
            r"credit risk", r"credit exposure", r"impairment", r"collateral",
            r"related part\w+", r"concentration", r"IFRS ?9", r"loan",
            r"credit facilit\w+", r"credit extension", r"troubled credit", r"provision\w* for",
            r"international financial reporting standard", r"credit information",
        ),
        he_subjects=("סיכון אשראי", "הלוואות וחובות", "ערבויות",
                     "הלוואות לדיור"),
    ),
    Category(
        id="capital_liquidity",
        name="Capital & liquidity",
        description="Capital adequacy, Basel III, leverage, liquidity "
                    "ratios, systemic banks and distributions.",
        orm_core=False,
        keywords=(
            r"capital adequacy", r"regulatory capital", r"minimum capital",
            r"basel", r"leverage", r"liquidity", r"\bLCR\b", r"\bNSFR\b",
            r"systemically important", r"D-SIB", r"dividend",
        ),
        he_subjects=("הלימות ההון ומינוף", "נזילות", "חלוקה (דיבידנד ורכישה)"),
    ),
    Category(
        id="market",
        name="Market & interest-rate risk",
        description="Market risk, interest-rate risk, foreign currency, "
                    "derivatives and capital-market activity.",
        orm_core=False,
        keywords=(
            r"market risk", r"interest rate", r"foreign currenc\w+",
            r"derivative", r"securities", r"futures", r"LIBOR",
            r"capital market", r"precious metals", r"margin basis",
            r"stocks", r"capital shares",
        ),
        he_subjects=("סיכוני שוק", "ריבית", "Interest rate risk",
                     "פעילויות שוק ההון", "ניירות ערך"),
    ),
    Category(
        id="climate",
        name="Climate & environmental risk",
        description="Climate-related and environmental financial risks.",
        orm_core=False,
        keywords=(r"climate", r"environmental", r"\bESG\b", r"sustainab\w+"),
        he_subjects=("סיכונים סביבתיים",),
    ),
    Category(
        id="licensing",
        name="Licensing & structure",
        description="Licensing, new banks, branching, ownership and "
                    "non-bank financial entities.",
        orm_core=False,
        keywords=(
            r"licens\w+", r"new bank\w*", r"branch\w*", r"money exchange",
            r"microfinance", r"ownership", r"control (or|and) (substantial )?"
            r"(holding|noncontrolling)", r"establishing",
        ),
        he_subjects=("בנקים חדשים", "תאגידים בנקאיים ייחודיים ותאגידים אחרים"),
    ),
)

BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}

HE_SUBJECT_TO_CATEGORY: dict[str, str] = {
    subject: c.id for c in CATEGORIES for subject in c.he_subjects
}

ALL_EXPECTATIONS: tuple[tuple[str, Expectation], ...] = tuple(
    (c.id, e) for c in CATEGORIES for e in c.expectations
)


def orm_core_ids() -> list[str]:
    return [c.id for c in CATEGORIES if c.orm_core]
