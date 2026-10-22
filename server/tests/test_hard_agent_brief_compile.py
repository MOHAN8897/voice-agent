"""Hard compile suite — messy, incomplete, mixed-role briefs people actually type."""
from __future__ import annotations

import re

import pytest

from server.brain.agent_script_compiler import (
    _looks_like_agent_name,
    compile_agent_from_brief,
)

# 20 real-world-ish briefs: typos, ambiguity, half-info, mixed industries.
HARD_BRIEFS: list[dict] = [
    {
        "id": "priya_auto_cars",
        "brief": (
            "the agent name is priya and a representative of business named auto cars private limited "
            "where servicing of automobiles are provided at reasonable prices, office located in hyderabad. "
            "we offer inspection, resale, consultation, repairing etc. we are in this buisness for about 20 years"
        ),
        "name": "Priya",
        "company_contains": "Auto Cars",
        "facts": ["inspection", "hyderabad"],
        "role": "sales",
        "must_not": ["You are Auto Cars"],
    },
    {
        "id": "typo_ravi_dental",
        "brief": "agnet name ravi frm smylecare denal clinic hydrabad book tooth pain appointments",
        "name": "Ravi",
        "company_contains": "Smylecare",
        "facts": ["tooth", "appointment"],
        "role": "appointment",
    },
    {
        "id": "company_only_sales",
        "brief": "Create outbound sales agent for GreenHomes Realty. Sell 2BHK flats from 45 lakhs in Gachibowli.",
        "name": "Priya",
        "company_contains": "GreenHomes",
        "facts": ["45 lakhs", "2BHK"],
        "role": "sales",
        "invented_name_ok": True,
    },
    {
        "id": "person_only_no_company",
        "brief": "Agent named Kavya. Call people who asked about our spoken english course. Trial class saturday. Fee 8000.",
        "name": "Kavya",
        "no_company": True,
        "facts": ["8000", "spoken"],
        "role": "education",
        "must_not": ["Acme", "GreenHomes"],
    },
    {
        "id": "vague_shop",
        "brief": "make a bot for my shop we sell stuff please call customers",
        "invented_name_ok": True,
        "no_company": True,
        "must_not": ["Private Limited", "Acme", "plots", "50 lakhs"],
    },
    {
        "id": "half_info_course",
        "brief": "call people about our course 8000 rupees",
        "invented_name_ok": True,
        "no_company": True,
        "facts": ["8000"],
        "must_not": ["site visit", "2BHK"],
    },
    {
        "id": "two_names_conflict",
        "brief": "agent name is Kavya also people call her Meera from GreenHomes Realty selling plots",
        "name": "Kavya",
        "company_contains": "GreenHomes",
        "facts": ["plots"],
        "must_not": ["You are Meera"],
    },
    {
        "id": "named_after_company_trap",
        "brief": "I am the owner. The agent should speak for company SKM Plants. Don't invent a second brand. Sell indoor plants.",
        "company_contains": "SKM",
        "invented_name_ok": True,
        "must_not": ["You are SKM Plants"],
        "facts": ["plants"],
    },
    {
        "id": "inbound_support_fiber",
        "brief": "inbound support for billing issues at CityFiber. Agent name Neha. Do not sell. Fix failed payments.",
        "name": "Neha",
        "company_contains": "CityFiber",
        "facts": ["billing"],
        "role": "support",
        "inbound": True,
        "must_not": ["site visit", "Do you have a moment?"],
    },
    {
        "id": "recruit_arjun",
        "brief": "hire drivers for FastHaul logistics agent named Arjun. Salary is not in this brief. Never invent salary.",
        "name": "Arjun",
        "company_contains": "FastHaul",
        "role": "recruitment",
        "must_not": ["₹", "lakh salary", "site visit"],
    },
    {
        "id": "education_ananya",
        "brief": "Ananya for Horizon Learning Institute in Hyderabad. Spoken English. Intermediate fee eight thousand. Trial class.",
        "name": "Ananya",
        "company_contains": "Horizon",
        "facts": ["eight thousand", "trial"],
        "role": "education",
    },
    {
        "id": "mohan_vs_tis",
        "brief": (
            "name is mohan, realted to bindusara agencies working in real estate "
            "create a agent naed tis who should convince the users to buy plots in our venture near ORR"
        ),
        "name": "Tis",
        "company_contains": "Bindusara",
        "facts": ["plots"],
        "must_not": ["You are Mohan", "mohan"],
        "role": "sales",
    },
    {
        "id": "callback_only",
        "brief": "dont sell just collect callback for WellnessHub. Agent: Sita. Follow up people who requested a callback last week.",
        "name": "Sita",
        "company_contains": "WellnessHub",
        "role": "follow_up",
        "must_not": ["site visit"],
    },
    {
        "id": "telugu_name_company_is",
        "brief": "agent name దీప్తి company is Sai Dental. Book dentist appointments in Ameerpet.",
        "name": "దీప్తి",
        "company_contains": "Sai Dental",
        "role": "appointment",
        "facts": ["dentist"],
    },
    {
        "id": "wall_of_text",
        "brief": (
            "ok so basically we need someone like ramesh who will call from loantree pvt ltd "
            "about personal loans in hyderabad no email tools connected just talk and if they want "
            "callback note it interest rates not in brief never invent rates"
        ),
        "name": "Ramesh",
        "company_contains": "Loantree",
        "facts": ["hyderabad"],
        "must_not": ["12%", "interest rate is"],
    },
    {
        "id": "cheap_no_price",
        "brief": "We are cheap and best car wash in madhapur. Agent Meera. BrightShine. No prices in this brief.",
        "name": "Meera",
        "company_contains": "BrightShine",
        "must_not": ["₹", "rupees", "99", "199", "499"],
        "facts": ["madhapur"],
    },
    {
        "id": "two_cities_solar",
        "brief": "office in hyderabad and vizag, agent neha, company BrightSolar, rooftop solar consult, no site visit unless they ask",
        "name": "Neha",
        "company_contains": "BrightSolar",
        "facts": ["hyderabad", "vizag", "solar"],
    },
    {
        "id": "appointment_meera_smilecare",
        "brief": "Create an English appointment agent named Meera for SmileCare Dental. Book dentist appointments.",
        "name": "Meera",
        "company_contains": "SmileCare",
        "role": "appointment",
        "facts": ["dentist"],
    },
    {
        "id": "followup_loantree",
        "brief": "Follow up with people who requested a callback last week about a pending loan application. Agent Ramesh at LoanTree. Do not restart a sales pitch.",
        "name": "Ramesh",
        "company_contains": "LoanTree",
        "role": "follow_up",
    },
    {
        "id": "garbage_ambiguous",
        "brief": "asdf maybe cars or plants or something call them idk agent ??? ",
        "invented_name_ok": True,
        "no_company": True,
        "must_not": ["You are Asdf", "Private Limited", "50 lakhs", "2BHK"],
    },
]


_BOILERPLATE = (
    "create an agent",
    "create a agent",
    "agent name is",
    "agnet name",
    "the where ",
    "realted to",
    "naed ",
    "who should convince",
)


def _issues_for(case: dict, result, compiled: str) -> list[str]:
    issues: list[str] = []
    script = result.agent_script or ""
    name = result.agent_name or ""
    company = result.company_name or ""
    opening = ""
    if "--- CANONICAL OPENING ---" in script:
        opening = script.split("--- CANONICAL OPENING ---", 1)[1].split("---", 1)[0]

    if "--- AGENT IDENTITY ---" not in script:
        issues.append("missing AGENT IDENTITY")
    if "--- COMPANY & OFFER ---" not in script:
        issues.append("missing COMPANY & OFFER")
    if "--- CANONICAL OPENING ---" not in script:
        issues.append("missing CANONICAL OPENING")
    if "--- YOUR ROLE ON THIS CALL ---" not in script:
        issues.append("missing YOUR ROLE")

    if not _looks_like_agent_name(name):
        issues.append(f"agent_name is not a person: {name!r}")
    if company and name.lower() == company.lower():
        issues.append("agent_name equals company_name")
    if f"You are {name}" not in script:
        issues.append("identity line missing person name")
    if re.search(rf"You are {re.escape(company)}\.", script) if company else None:
        issues.append("identity treats company as the speaker")

    expected_name = case.get("name")
    if expected_name and name.lower() != expected_name.lower():
        issues.append(f"name {name!r} != {expected_name!r}")
    if case.get("invented_name_ok") and not expected_name:
        if not _looks_like_agent_name(name):
            issues.append(f"failed to invent a person name: {name!r}")

    needle = case.get("company_contains")
    if needle and needle.lower() not in company.lower():
        issues.append(f"company {company!r} missing {needle!r}")
    if "agent named" in company.lower() or company.lower().startswith("agent "):
        issues.append(f"company swallowed agent clause: {company!r}")
    if case.get("no_company") and company:
        issues.append(f"invented company {company!r}")

    if name and name.lower() not in opening.lower():
        issues.append("opening missing agent name")
    if company and company.split()[0].lower() not in opening.lower():
        issues.append("opening missing company")
    if case.get("inbound") and "Do you have a moment?" in opening:
        issues.append("inbound support used outbound permission opening")

    offer = script.split("--- COMPANY & OFFER ---", 1)[-1].split("---", 1)[0].lower() if "--- COMPANY & OFFER ---" in script else ""
    for blob in _BOILERPLATE:
        if blob in offer:
            issues.append(f"offer leaked boilerplate: {blob!r}")

    for fact in case.get("facts") or []:
        if fact.lower() not in script.lower() and fact.lower() not in compiled.lower():
            issues.append(f"missing fact {fact!r}")
    for banned in case.get("must_not") or []:
        if banned.lower() in script.lower():
            issues.append(f"script contains banned {banned!r}")

    expected_role = case.get("role")
    if expected_role and result.detected_role != expected_role:
        issues.append(f"role {result.detected_role!r} != {expected_role!r}")

    if "Never claim to be anyone except" in compiled and name and name not in compiled:
        issues.append("brain guardrail missing agent name")
    if case.get("inbound"):
        if "Wait for the callee to speak first" in compiled:
            issues.append("inbound brain still has outbound wait-for-callee workflow")
        if "Never use help-desk language on the first turn" in compiled:
            issues.append("inbound support forbidden from help-desk first turn")
    else:
        if "How can I help you today?" in opening:
            issues.append("outbound opening used inbound help-desk phrasing")

    return issues


@pytest.mark.asyncio
@pytest.mark.parametrize("case", HARD_BRIEFS, ids=[c["id"] for c in HARD_BRIEFS])
async def test_hard_brief_compiles_clean_script(case):
    compiled, result, *_ = await compile_agent_from_brief(
        brief=case["brief"],
        language="en-IN",
        use_llm=False,
    )
    issues = _issues_for(case, result, compiled)
    assert not issues, f"{case['id']}: " + "; ".join(issues)
