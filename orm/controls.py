"""Starter library of operational-risk controls.

Generic controls a bank's risk, compliance and audit functions typically run,
grouped by the risk taxonomy (orm.taxonomy). They are written for this tool,
not taken from any regulator or framework, and are a starting point: each
bank replaces or extends them with its own control set (see orm.coverage).

`keywords` are regex fragments used to suggest which control answers an
obligation (orm.obligations.map_controls). Suggestions are reviewed by a
person before they reach a report.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Control:
    id: str
    category_id: str
    name: str
    description: str
    frequency: str
    evidence: str
    keywords: tuple[str, ...]


def _c(id, category_id, name, description, frequency, evidence, *keywords):
    return Control(id, category_id, name, description, frequency, evidence, keywords)


LIBRARY: tuple[Control, ...] = (
    # --- Governance & risk framework -------------------------------------------
    _c("GOV-01", "governance", "Board approval of the risk management framework",
       "The board approves the risk management framework and policies, and "
       "re-approves them after material change.", "Annually",
       "Board minutes and approved framework document",
       r"board", r"approv", r"framework", r"polic"),
    _c("GOV-02", "governance", "Risk appetite statement set and monitored",
       "A documented risk appetite with limits is approved and breaches are "
       "escalated.", "Annually; breaches as they occur",
       "Approved risk appetite statement; limit breach reports",
       r"risk appetite", r"limit", r"toleran"),
    _c("GOV-03", "governance", "Independent risk management function",
       "A risk function headed by a CRO, independent of the business, with a "
       "reporting line to the board.", "Ongoing; reviewed annually",
       "Org chart, CRO mandate, reporting-line records",
       r"chief risk officer", r"risk management function", r"independen"),
    _c("GOV-04", "governance", "Compliance function and compliance plan",
       "A compliance officer runs an annual compliance plan and reports "
       "findings to management and the board.", "Annually",
       "Compliance plan, compliance reports to the board",
       r"complian", r"compliance officer"),
    _c("GOV-05", "governance", "Internal audit coverage of risk areas",
       "Internal audit runs a risk-based plan covering all material risk "
       "areas and tracks findings to closure.", "Annual plan; findings tracked continuously",
       "Approved audit plan, audit reports, findings tracker",
       r"internal audit", r"audit"),
    _c("GOV-06", "governance", "Board and committee reporting on risk",
       "Management reports the risk profile, incidents and limit use to the "
       "board or its risk committee.", "Quarterly",
       "Risk reports and committee minutes",
       r"report\w* to the board", r"committee", r"senior management"),
    _c("GOV-07", "governance", "Policies reviewed and kept current",
       "Each policy has an owner and is reviewed and re-approved on schedule.",
       "Annually", "Policy register with review dates and approvals",
       r"review\w* (the )?polic", r"update", r"at least once a year", r"annual"),
    _c("GOV-08", "governance", "Document and record retention",
       "Records required by regulation are retained for the required period "
       "and can be retrieved.", "Ongoing; tested annually",
       "Retention schedule; retrieval test results",
       r"retain", r"retention", r"record", r"documentation"),

    # --- Operational risk & resilience -----------------------------------------
    _c("RES-01", "op_resilience", "Business continuity plan maintained",
       "A documented BCP covers critical activities, with roles, recovery "
       "steps and communication.", "Reviewed annually",
       "Approved BCP with version history",
       r"business continuity", r"continuity plan", r"\bbcp\b"),
    _c("RES-02", "op_resilience", "Recovery time and point objectives defined",
       "RTO and RPO are set for each critical activity and system and "
       "approved.", "Annually",
       "Business impact analysis with RTO/RPO",
       r"recovery time", r"recovery point", r"\brto\b", r"\brpo\b", r"impact analysis"),
    _c("RES-03", "op_resilience", "Continuity and disaster recovery testing",
       "BCP and DR arrangements are tested, results documented and issues "
       "remediated.", "At least annually",
       "Test plans, test reports, remediation log",
       r"test", r"drill", r"exercise", r"disaster recovery"),
    _c("RES-04", "op_resilience", "Severe but plausible scenario analysis",
       "Scenario analysis tests the bank's ability to stay within tolerance "
       "under severe disruption.", "Annually",
       "Scenario analysis report",
       r"scenario", r"stress", r"severe but plausible"),
    _c("RES-05", "op_resilience", "Operational loss and event data collection",
       "Operational losses and events are recorded, classified and analysed.",
       "Continuous; reported quarterly",
       "Loss event database extract; loss reports",
       r"loss data", r"loss event", r"operational (risk )?event", r"database"),
    _c("RES-06", "op_resilience", "Operational risk self-assessment",
       "Business units assess their operational risks and controls (RCSA) "
       "and track actions.", "Annually",
       "RCSA results and action tracker",
       r"self[- ]assess", r"identif\w* (and|,) assess", r"risk assessment"),
    _c("RES-07", "op_resilience", "Crisis management and escalation",
       "A crisis management team, escalation paths and communication plans "
       "are defined and rehearsed.", "Rehearsed annually",
       "Crisis plan, contact lists, rehearsal record",
       r"crisis", r"emergenc", r"escalat"),

    # --- Outsourcing & third-party ---------------------------------------------
    _c("TPR-01", "third_party", "Outsourcing policy and register",
       "An approved outsourcing policy and a register of all outsourcing "
       "arrangements with criticality.", "Register updated continuously; policy annually",
       "Outsourcing policy; outsourcing register",
       r"outsourc\w* polic", r"register", r"inventory"),
    _c("TPR-02", "third_party", "Due diligence before engaging a provider",
       "Providers are assessed (financial, operational, security, "
       "concentration) before contracting.", "Before each engagement",
       "Due diligence file and approval",
       r"due diligence", r"assess\w* (the )?(service )?provider", r"select"),
    _c("TPR-03", "third_party", "Contract terms: audit, access, SLAs",
       "Contracts include audit and access rights for the bank and the "
       "supervisor, SLAs, security and termination terms.", "Each contract",
       "Executed contract with clause checklist",
       r"contract", r"agreement", r"right\w* of (audit|access)", r"service level"),
    _c("TPR-04", "third_party", "Ongoing monitoring of providers",
       "Provider performance, risk and SLA compliance are monitored and "
       "reviewed.", "At least annually; critical providers quarterly",
       "Provider performance reviews",
       r"monitor", r"oversight", r"performance"),
    _c("TPR-05", "third_party", "Exit strategy for critical outsourcing",
       "Documented, tested exit plans exist for critical outsourced "
       "services.", "Reviewed annually",
       "Exit plans and test evidence",
       r"exit", r"terminat", r"transition", r"substitut"),
    _c("TPR-06", "third_party", "Supervisor notification of material outsourcing",
       "The supervisor is notified of, or approves, material outsourcing "
       "before it starts.", "Before each material arrangement",
       "Notification or approval correspondence",
       r"notif", r"approval of the supervisor", r"prior (written )?approval", r"supervisor"),
    _c("TPR-07", "third_party", "Cloud and data-location controls",
       "Cloud use is assessed for security, data location, and concentration, "
       "and approved.", "Before adoption; reviewed annually",
       "Cloud risk assessment; data location records",
       r"cloud", r"data location", r"jurisdiction"),

    # --- IT, cyber & information security --------------------------------------
    _c("ICT-01", "ict_cyber", "Information security policy",
       "An approved information security policy sets roles, standards and "
       "responsibilities.", "Annually",
       "Approved information security policy",
       r"information security", r"security polic", r"cyber\w* polic"),
    _c("ICT-02", "ict_cyber", "Access management and privileged access review",
       "Access is granted on least privilege; privileged and user access is "
       "reviewed and revoked when no longer needed.", "Quarterly reviews",
       "Access review sign-offs",
       r"access", r"privileg", r"authori[sz]", r"identity"),
    _c("ICT-03", "ict_cyber", "Vulnerability management and patching",
       "Systems are scanned for vulnerabilities and patched within set "
       "timeframes.", "Monthly scans; patching per severity",
       "Scan reports; patch compliance reports",
       r"vulnerab", r"patch", r"penetration"),
    _c("ICT-04", "ict_cyber", "Security monitoring and detection",
       "Security events are logged, monitored (e.g. SOC) and investigated.",
       "Continuous", "Monitoring coverage report; incident tickets",
       r"monitor", r"log\w*", r"detect", r"security operation"),
    _c("ICT-05", "ict_cyber", "Backup and restoration testing",
       "Data and systems are backed up and restores are tested.",
       "Backups daily; restore tests at least annually",
       "Backup logs; restore test results",
       r"backup", r"back-up", r"restor"),
    _c("ICT-06", "ict_cyber", "Change management for IT systems",
       "Changes to production systems are approved, tested and recorded.",
       "Each change", "Change tickets with approvals and test evidence",
       r"change management", r"chang\w* to (the )?system", r"development"),
    _c("ICT-07", "ict_cyber", "Penetration testing and cyber assessments",
       "Independent penetration tests and cyber maturity assessments are "
       "performed and findings remediated.", "At least annually",
       "Test reports and remediation tracker",
       r"penetration", r"red team", r"assessment", r"maturity"),
    _c("ICT-08", "ict_cyber", "Security awareness training",
       "Staff receive security awareness training, including phishing "
       "exercises.", "Annually", "Training completion records",
       r"training", r"awareness", r"staff"),

    # --- Incident & event reporting --------------------------------------------
    _c("INC-01", "incident_reporting", "Incident management procedure",
       "A procedure classifies incidents by severity and sets response and "
       "escalation steps.", "Reviewed annually",
       "Approved incident procedure",
       r"incident", r"classif", r"severity"),
    _c("INC-02", "incident_reporting", "Regulatory incident notification",
       "Significant incidents are reported to the supervisor within the "
       "required deadline.", "Per incident, within deadline",
       "Notifications sent with timestamps",
       r"notif", r"report\w* to the supervis", r"within \d+ hours", r"immediately"),
    _c("INC-03", "incident_reporting", "Incident register",
       "All incidents are recorded with impact, root cause and status.",
       "Continuous", "Incident register extract",
       r"register", r"record", r"log"),
    _c("INC-04", "incident_reporting", "Root cause analysis and follow-up",
       "Significant incidents get a root-cause analysis and tracked "
       "corrective actions.", "Per significant incident",
       "RCA reports; action tracker",
       r"root cause", r"lessons", r"corrective", r"follow[- ]up"),
    _c("INC-05", "incident_reporting", "Incident reporting to the board",
       "Material incidents and trends are reported to management and the "
       "board.", "Quarterly", "Board/committee incident reports",
       r"board", r"management", r"report"),

    # --- AML/CFT & sanctions ---------------------------------------------------
    _c("AML-01", "aml", "Customer due diligence and KYC",
       "Customers are identified and verified, risk-rated, and refreshed "
       "periodically.", "At onboarding; periodic refresh by risk",
       "KYC files; refresh reports",
       r"customer due diligence", r"know your customer", r"\bkyc\b", r"identif\w* (the )?customer", r"verif"),
    _c("AML-02", "aml", "Transaction monitoring",
       "Transactions are monitored for suspicious activity and alerts are "
       "investigated.", "Continuous", "Alert logs and investigation records",
       r"monitor", r"transaction", r"unusual"),
    _c("AML-03", "aml", "Suspicious activity reporting",
       "Suspicious transactions are reported to the financial intelligence "
       "unit on time.", "Per case", "Filed reports with dates",
       r"suspicious", r"report", r"financial intelligence", r"\bstr\b|\bsar\b"),
    _c("AML-04", "aml", "Sanctions screening",
       "Customers and payments are screened against sanctions lists.",
       "Continuous; lists updated daily", "Screening logs; hit resolution records",
       r"sanction", r"screen", r"list"),
    _c("AML-05", "aml", "AML risk assessment and training",
       "An enterprise AML risk assessment is performed and staff are "
       "trained.", "Annually", "AML risk assessment; training records",
       r"risk assessment", r"training", r"money laundering"),

    # --- Conduct & consumer protection -----------------------------------------
    _c("CON-01", "conduct", "Customer disclosure and fair terms",
       "Product terms, fees and risks are disclosed clearly before the "
       "customer commits.", "Each product; reviewed annually",
       "Disclosure documents; product approval records",
       r"disclos", r"inform\w* the customer", r"fee", r"terms"),
    _c("CON-02", "conduct", "Complaints handling",
       "Complaints are recorded, answered within set times, and analysed "
       "for root causes.", "Continuous; reported quarterly",
       "Complaints register and reports",
       r"complain", r"public inquir", r"response"),
    _c("CON-03", "conduct", "Product approval and suitability",
       "New products are approved with a risk and suitability assessment.",
       "Before each launch", "Product approval records",
       r"product", r"suitab", r"appropriat"),
    _c("CON-04", "conduct", "Advertising and communications review",
       "Marketing material is reviewed for accuracy and compliance before "
       "release.", "Each campaign", "Review sign-offs",
       r"advertis", r"marketing", r"communication"),
    _c("CON-05", "conduct", "Customer data protection and privacy",
       "Customer data is protected and used only as permitted.",
       "Ongoing; reviewed annually", "Privacy assessments; access logs",
       r"privacy", r"confidential", r"personal data", r"secrecy"),
)

BY_ID = {c.id: c for c in LIBRARY}


def for_category(category_id: str) -> list[Control]:
    return [c for c in LIBRARY if c.category_id == category_id]
