"""Native US/UK English compile suite — hard briefs, no Indian-English leakage."""
from __future__ import annotations

import re

import pytest

from server.brain.agent_script_compiler import (
    _looks_like_agent_name,
    compile_agent_from_brief,
)

NATIVE_BRIEFS: list[dict] = [
    {
        "id": "saas_outbound_usd",
        "brief": (
            "Outbound sales for Northwind Labs. Agent name Sarah. "
            "SaaS at $49 per month. Book a demo. Never invent discounts."
        ),
        "name": "Sarah",
        "company_contains": "Northwind",
        "facts": ["49"],
        "role": "sales",
        "must_not": ["rupees", "lakh", "WhatsApp", "visit/callback", "site visit"],
    },
    {
        "id": "uk_dentist",
        "brief": "Create an English appointment agent named James for Oak Street Dental in London. Book dentist appointments. Fees are ninety nine pounds.",
        "name": "James",
        "company_contains": "Oak Street Dental",
        "role": "appointment",
        "facts": ["ninety nine"],
        "must_not": ["rupees", "lakh"],
    },
    {
        "id": "inbound_billing_us",
        "brief": "inbound support for billing issues at CityFiber. Agent name Emma. Do not sell. Fix failed payments.",
        "name": "Emma",
        "company_contains": "CityFiber",
        "role": "support",
        "inbound": True,
        "must_not": ["Do you have a moment?", "site visit", "rupees"],
    },
    {
        "id": "recruit_austin",
        "brief": "hire drivers for FastHaul logistics agent named Marcus. Salary is not in this brief. Never invent salary.",
        "name": "Marcus",
        "company_contains": "FastHaul",
        "role": "recruitment",
        "must_not": ["lakh", "rupees", "site visit"],
    },
    {
        "id": "bootcamp_usd",
        "brief": "Agent named Ava. Call people who asked about our coding bootcamp. Trial class Saturday. Fee 8000 dollars.",
        "name": "Ava",
        "no_company": True,
        "facts": ["8000"],
        "role": "education",
        "must_not": ["lakh", "rupees", "Acme"],
    },
    {
        "id": "austin_realty",
        "brief": "Create outbound sales agent for GreenHomes Realty. Sell 2 bedroom homes from 450000 dollars in Austin.",
        "invented_name_ok": True,
        "company_contains": "GreenHomes",
        "facts": ["450000"],
        "role": "sales",
        "must_not": ["rupees", "lakh"],
    },
    {
        "id": "vague_shop_us",
        "brief": "make a bot for my shop we sell stuff please call customers",
        "invented_name_ok": True,
        "no_company": True,
        "must_not": ["Private Limited", "lakh", "rupees", "2BHK"],
    },
    {
        "id": "typo_us_clinic",
        "brief": "agnet name ravi frm smylecare denal clinic austin book tooth pain appointments",
        "name": "Ravi",
        "company_contains": "Smylecare",
        "role": "appointment",
    },
    {
        "id": "followup_loan_us",
        "brief": "Follow up with people who requested a callback last week about a pending loan application. Agent Ramesh at LoanTree. Do not restart a sales pitch.",
        "name": "Ramesh",
        "company_contains": "LoanTree",
        "role": "follow_up",
        "must_not": ["site visit"],
    },
    {
        "id": "callback_only_us",
        "brief": "dont sell just collect callback for WellnessHub. Agent: Sita. Follow up people who requested a callback last week.",
        "name": "Sita",
        "company_contains": "WellnessHub",
        "role": "follow_up",
        "must_not": ["site visit"],
    },
    {
        "id": "solar_california",
        "brief": "office in Austin and Dallas, agent neha, company BrightSolar, rooftop solar consult, no site visit unless they ask",
        "name": "Neha",
        "company_contains": "BrightSolar",
        "facts": ["austin", "dallas", "solar"],
    },
    {
        "id": "named_after_company_us",
        "brief": "I am the owner. The agent should speak for company SKM Plants. Don't invent a second brand. Sell indoor plants.",
        "company_contains": "SKM",
        "invented_name_ok": True,
        "must_not": ["You are SKM Plants"],
        "facts": ["plants"],
    },
    {
        "id": "two_names_us",
        "brief": "agent name is Kavya also people call her Meera from GreenHomes Realty selling plots",
        "name": "Kavya",
        "company_contains": "GreenHomes",
        "must_not": ["You are Meera"],
    },
    {
        "id": "half_info_course_us",
        "brief": "call people about our course 8000 dollars",
        "invented_name_ok": True,
        "no_company": True,
        "facts": ["8000"],
        "must_not": ["2BHK", "lakh"],
    },
    {
        "id": "healthcare_inbound",
        "brief": "inbound support for Northstar Health. Agent Olivia. Help with appointment reminders. Do not sell.",
        "name": "Olivia",
        "company_contains": "Northstar",
        "inbound": True,
        "must_not": ["Do you have a moment?", "rupees"],
    },
    {
        "id": "mohan_vs_tis_us",
        "brief": (
            "name is mohan, realted to bindusara agencies working in real estate "
            "create a agent naed tis who should convince the users to buy plots in our venture near ORR"
        ),
        "name": "Tis",
        "company_contains": "Bindusara",
        "facts": ["plots"],
        "must_not": ["You are Mohan"],
        "role": "sales",
    },
    {
        "id": "cheap_no_price_us",
        "brief": "We are cheap and best car wash in Austin. Agent Meera. BrightShine. No prices in this brief.",
        "name": "Meera",
        "company_contains": "BrightShine",
        "must_not": ["rupees", "lakh", "499"],
        "facts": ["austin"],
    },
    {
        "id": "wall_of_text_us",
        "brief": (
            "ok so basically we need someone like ramesh who will call from loantree pvt ltd "
            "about personal loans in dallas no email tools connected just talk and if they want "
            "callback note it interest rates not in brief never invent rates"
        ),
        "name": "Ramesh",
        "company_contains": "Loantree",
        "must_not": ["12%", "interest rate is", "lakh"],
    },
    {
        "id": "unnamed_invents_alex",
        "brief": "Outbound sales for car servicing in Austin. Inspection, resale, and repairs.",
        "name": "Alex",
        "no_company": True,
    },
    {
        "id": "garbage_us",
        "brief": "asdf maybe cars or plants or something call them idk agent ??? ",
        "invented_name_ok": True,
        "no_company": True,
        "must_not": ["You are Asdf", "lakh", "rupees", "50 lakhs"],
    },
]


_INDIAN_LEAK = (
    "spoken indian english",
    "konchem",
    "nenu ",
    "meeru ",
    "rupees fifty",
)


def _issues_for(case: dict, result, compiled: str) -> list[str]:
    issues: list[str] = []
    script = result.agent_script or ""
    name = result.agent_name or ""
    company = result.company_name or ""
    opening = ""
    if "--- CANONICAL OPENING ---" in script:
        opening = script.split("--- CANONICAL OPENING ---", 1)[1].split("---", 1)[0]
    blob = f"{script}\n{compiled}".lower()

    if "--- AGENT IDENTITY ---" not in script:
        issues.append("missing AGENT IDENTITY")
    if "--- COMPANY & OFFER ---" not in script:
        issues.append("missing COMPANY & OFFER")
    if "--- CANONICAL OPENING ---" not in script:
        issues.append("missing CANONICAL OPENING")

    if not _looks_like_agent_name(name):
        issues.append(f"agent_name is not a person: {name!r}")
    if company and name.lower() == company.lower():
        issues.append("agent_name equals company_name")
    if f"You are {name}" not in script:
        issues.append("identity line missing person name")

    expected_name = case.get("name")
    if expected_name and name.lower() != expected_name.lower():
        issues.append(f"name {name!r} != {expected_name!r}")
    if case.get("invented_name_ok") and not expected_name:
        if not _looks_like_agent_name(name):
            issues.append(f"failed to invent a person name: {name!r}")

    needle = case.get("company_contains")
    if needle and needle.lower() not in company.lower():
        issues.append(f"company {company!r} missing {needle!r}")
    if case.get("no_company") and company:
        issues.append(f"invented company {company!r}")
    if "agent named" in company.lower():
        issues.append(f"company swallowed agent clause: {company!r}")

    if name and name.lower() not in opening.lower():
        issues.append("opening missing agent name")
    if case.get("inbound") and (
        "Do you have a moment?" in opening or "Do you have a minute?" in opening
    ):
        issues.append("inbound used outbound permission opening")

    for fact in case.get("facts") or []:
        if fact.lower() not in script.lower() and fact.lower() not in compiled.lower():
            issues.append(f"missing fact {fact!r}")
    for banned in case.get("must_not") or []:
        if banned.lower() in script.lower():
            issues.append(f"script contains banned {banned!r}")

    expected_role = case.get("role")
    if expected_role and result.detected_role != expected_role:
        issues.append(f"role {result.detected_role!r} != {expected_role!r}")

    for leak in _INDIAN_LEAK:
        if leak in blob and leak not in (case.get("brief") or "").lower():
            issues.append(f"native English brain leaked {leak!r}")

    if "spoken indian english" in compiled.lower():
        issues.append("brain still says spoken Indian English")
    if re.search(r"[\u0c00-\u0c7f]", compiled):
        issues.append("brain contains Telugu script")

    if case.get("inbound"):
        if "Wait for the callee to speak first" in compiled:
            issues.append("inbound brain still has outbound wait-for-callee")
    return issues


@pytest.mark.asyncio
@pytest.mark.parametrize("case", NATIVE_BRIEFS, ids=[c["id"] for c in NATIVE_BRIEFS])
async def test_native_english_brief_compiles_clean_script(case):
    compiled, result, *_ = await compile_agent_from_brief(
        brief=case["brief"],
        language="en-US",
        use_llm=False,
    )
    issues = _issues_for(case, result, compiled)
    assert not issues, f"{case['id']}: " + "; ".join(issues)
    assert "natural spoken English" in compiled or "US/UK" in compiled or "en-US" in compiled
