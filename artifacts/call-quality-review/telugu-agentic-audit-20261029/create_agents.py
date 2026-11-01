"""Create and publish three genuinely different Telugu business agents.

Follows the real website pipeline:
analyze_employee_brief -> clarification -> compile_brief_for_employee -> publish_saas_employee_brain.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 stdout
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT_DIR = Path(__file__).resolve().parent

from server.config import get_settings
from server.db.connection import init_db, close_db, get_session_factory
from server.db.tier_store import load_tier_cache
from server.db.models.entities import Tenant, Agent
from server.brain.employee_script_pipeline import (
    analyze_employee_brief,
    clarification_response,
    ClarificationAnswer,
)
from server.services.saas.employee_brain_build import (
    compile_brief_for_employee,
    publish_saas_employee_brain,
)
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.capabilities import compile_agent_capabilities
from server.providers.resolver import resolve_stack

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audit_create_agents")

# 1. Digital Printing Business Definition & Predefined Fact Sheet
PRINTING_BRIEF = """Agent name Kavitha. Company name Sri Krishna Digital Prints.
Outbound and inbound customer inquiries in Telugu.
We print visiting cards: normal paper visiting cards cost 200 rupees for 100 cards,
matte finish cards cost 350 rupees for 100 cards. Minimum order quantity 100 cards.
Wedding invitation cards are customized: pricing depends on design, paper sample and quantity, no fixed price over the phone.
Flex banners: normal flex 15 rupees per square foot, star flex 20 rupees per square foot.
Delivery in Vijayawada takes 3 working days after design artwork approval; urgent 24-hour delivery is extra 150 rupees.
Payment: Cash on delivery accepted for orders up to 1000 rupees; 50% advance payment required for orders above 1000 rupees.
No online payment or credit card processing on phone call.
Office hours Monday to Saturday 9:30 AM to 8:00 PM, Sunday closed.
Goal: answer customer questions on cards, banners and pricing; understand their requirement.
If interested, take preferred name, quantity and delivery locality for a quote or order request.
Do not force details before answering questions.
Customer refusing visiting cards may still want flex banners or wedding cards.
Never claim an order is paid or dispatched without artwork approval and design confirmation.
Language: te-IN."""

PRINTING_FACT_SHEET = {
    "agent_name": "Kavitha",
    "company_name": "Sri Krishna Digital Prints",
    "role": "Sales and customer enquiries",
    "permitted_next_steps": "Collect customer name, item type, quantity and delivery locality in Vijayawada to submit an internal quote/order request. Explain that artwork approval is required before printing.",
    "payment_rules": "Cash on delivery for orders up to 1000 rupees; 50% advance for orders above 1000 rupees. No online payment collection on call.",
    "delivery_details": "Local delivery in Vijayawada takes 3 working days after artwork approval. Urgent 24-hour delivery is extra 150 rupees.",
    "wedding_cards": "Customized quotation only based on design and paper sample. No fixed price on phone.",
    "visiting_cards": "Standard 200 rupees for 100 cards; Matte finish 350 rupees for 100 cards. Minimum order 100 cards.",
    "forbidden_actions": "Never confirm external courier shipment or take card payment on phone. Never guarantee delivery without artwork approval.",
}

# 2. Home/Appliance Services Business Definition & Predefined Fact Sheet
APPLIANCE_BRIEF = """Need helpful support agent Suresh for SmartCare Appliance Services.
Phone customer support and booking inquiries in Telugu.
Hyderabad home appliance repair and maintenance services.
AC servicing: basic Window AC servicing 499 rupees, Split AC servicing 599 rupees.
Fridge inspection charge 250 rupees; if repair is done by technician, inspection charge is completely waived.
Replacement parts are extra at actual MRP and technician quotes after inspection; no fixed parts quotes over phone.
Working days: Monday to Sunday 9:00 AM to 7:00 PM.
Service areas: Hyderabad West - Madhapur, Gachibowli, Kondapur, Kukatpally.
Secunderabad and Old City areas are currently not covered.
Slots: Next-day visit slots between 10 AM and 6 PM. Same-day emergency service not guaranteed.
Goal: answer service pricing and area questions honestly.
If customer requests appointment, take caller name, appliance type, issue, locality and preferred slot.
Never advise customer to open electrical panels or live wiring themselves.
Do not sell AMC contracts or courses. Caller declining AC may still need fridge service.
Language: te-IN."""

APPLIANCE_FACT_SHEET = {
    "agent_name": "Suresh",
    "company_name": "SmartCare Appliance Services",
    "role": "Support and service appointment booking",
    "permitted_next_steps": "Check locality and appliance issue; collect name, phone, address and preferred slot (10 AM - 6 PM next day) to book or request technician visit.",
    "service_areas": "Hyderabad West only: Madhapur, Gachibowli, Kondapur, Kukatpally. Secunderabad and Old City are not serviced.",
    "pricing_terms": "Split AC 599 rupees, Window AC 499 rupees. Fridge inspection 250 rupees (waived if repair accepted). Spare parts extra at actuals.",
    "safety_rules": "Never advise live electrical inspection. Tell customer to unplug faulty appliances and wait for certified technician.",
    "forbidden_actions": "Do not promise same-day visit or quote parts prices before technician inspection. No advance payment on call.",
}

# 3. Training/Course Business Definition & Predefined Fact Sheet
COURSE_BRIEF = """Agent name Madhavi, company Teja Data Academy.
Phone counselling and course admissions in Telugu.
We offer practical Python with Data Analytics certification course.
Duration: 8 weeks online live classes with hands-on projects.
Batches: Weekday batch 8:00 PM to 9:00 PM (Mon-Fri); Weekend batch 10:00 AM to 1:00 PM (Sat-Sun).
Fee: Final fee is 8,999 rupees total. An old leaflet mentions 12000/15000 rupees, discard that old fee. Current fee 8,999 rupees only.
No installment discounts.
Eligibility: Any graduate (BTech, BSc, BCom) or final year college student. Basic computer knowledge needed, prior coding not required.
Placement policy: 100% placement assistance provided (resume building, interview preparation, job referrals); strictly NO job guarantee or salary promise.
Goal: answer course curriculum, fees, batches and timing questions.
If interested in free demo session or admission counselling, collect preferred name, email, qualification and preferred batch.
No payment collected over the phone.
Refund policy: No refund once classes start after the first week.
Language: te-IN."""

COURSE_FACT_SHEET = {
    "agent_name": "Madhavi",
    "company_name": "Teja Data Academy",
    "role": "Course counselling and demo registration",
    "permitted_next_steps": "Collect student name, email, educational qualification and batch preference (weekday/weekend) to book a free demo class or counsellor callback.",
    "fee_terms": "Final course fee is 8,999 rupees total. Disregard any old fees. No installment discounts.",
    "placement_policy": "Placement assistance provided (interview prep, resume building, referrals); strictly no job guarantee.",
    "eligibility_rules": "Any graduate or final year student; no prior coding experience required.",
    "forbidden_actions": "Never guarantee a job, salary package or placement. Never collect fees or credit card numbers on call.",
}

BUSINESSES = [
    {
        "id": "A",
        "key": "printing",
        "tenant_id": "00000000-0000-5000-a000-000000000001",
        "name": "Sri Krishna Digital Prints",
        "agent_name": "Kavitha",
        "role": "sales",
        "industry": "printing",
        "brief": PRINTING_BRIEF,
        "facts": PRINTING_FACT_SHEET,
    },
    {
        "id": "B",
        "key": "appliances",
        "tenant_id": "00000000-0000-5000-a000-000000000002",
        "name": "SmartCare Appliance Services",
        "agent_name": "Suresh",
        "role": "support",
        "industry": "home_services",
        "brief": APPLIANCE_BRIEF,
        "facts": APPLIANCE_FACT_SHEET,
    },
    {
        "id": "C",
        "key": "academy",
        "tenant_id": "00000000-0000-5000-a000-000000000003",
        "name": "Teja Data Academy",
        "agent_name": "Madhavi",
        "role": "counsellor",
        "industry": "education",
        "brief": COURSE_BRIEF,
        "facts": COURSE_FACT_SHEET,
    },
]


def resolve_fact_answer(question: str, field: str, fact_sheet: dict[str, str]) -> str:
    """Match question to predefined fictional fact sheet without inventing facts."""
    q_lower = question.lower()
    f_lower = field.lower()
    for key, val in fact_sheet.items():
        if key in f_lower or any(word in q_lower for word in key.split("_")):
            return val
    # Fallback to general permitted steps or role facts
    if "next" in q_lower or "step" in q_lower or "action" in q_lower:
        return fact_sheet.get("permitted_next_steps", "")
    if "pay" in q_lower or "fee" in q_lower or "price" in q_lower or "cost" in q_lower:
        return fact_sheet.get("payment_rules") or fact_sheet.get("fee_terms") or fact_sheet.get("pricing_terms", "")
    return fact_sheet.get("permitted_next_steps", "")


async def create_and_publish_agent(b_info: dict) -> dict:
    logger.info(f"--- Processing Business {b_info['id']}: {b_info['name']} ({b_info['agent_name']}) ---")
    tenant_uuid = uuid.UUID(b_info["tenant_id"])
    agent_uuid = uuid.uuid5(tenant_uuid, f"agent-{b_info['key']}")
    factory = get_session_factory()

    # 1. Upsert Tenant in isolated database
    async with factory() as session:
        t = await session.get(Tenant, tenant_uuid)
        if not t:
            t = Tenant(tenant_id=tenant_uuid, name=b_info["name"], plan="dev", status="active")
            session.add(t)
            await session.commit()
            logger.info(f"Created synthetic tenant {tenant_uuid} for {b_info['name']}")

    # 2. Step 1: analyze_employee_brief
    gen_cfg = {
        "employeeName": b_info["agent_name"],
        "agentRole": b_info["role"],
        "callDirection": "outbound",
        "mode": "instant_lead",
        "industry": b_info["industry"],
        "naturalSpokenStyle": True,
    }

    logger.info(f"Analyzing brief for {b_info['agent_name']}...")
    extracted = await analyze_employee_brief(brief=b_info["brief"], language="te-IN", generation_config=gen_cfg)
    clarif = clarification_response(extracted)
    questions = clarif.get("questions") or []
    logger.info(f"Analyze returned {len(questions)} clarification questions.")

    # 3. Step 2: Answer clarifications using strictly predefined fact sheet
    answers: list[ClarificationAnswer] = []
    answered_log = []
    for q in questions:
        ans_text = resolve_fact_answer(q["question"], q["field"], b_info["facts"])
        if not ans_text:
            ans_text = "Refer to the business facts provided in the brief."
        c_ans = ClarificationAnswer(field=q["field"], question=q["question"], answer=ans_text)
        answers.append(c_ans)
        answered_log.append({
            "field": q["field"],
            "question": q["question"],
            "reason": q.get("reason", ""),
            "answer": ans_text,
        })
        logger.info(f"Answered Q [{q['field']}]: {q['question'][:80]} -> {ans_text[:80]}...")

    # 4. Step 3: compile_brief_for_employee
    logger.info(f"Compiling employee script for {b_info['agent_name']}...")
    compiled, script_result, variables = await compile_brief_for_employee(
        brief=b_info["brief"],
        language="te-IN",
        generation_config=gen_cfg,
        answers=answers,
    )
    logger.info(f"Compiled script: {len(compiled)} chars, agent_name={script_result.agent_name}, role={script_result.role_summary}")

    # 5. Create Agent record in Postgres
    async with factory() as session:
        ag = await session.get(Agent, agent_uuid)
        if not ag:
            ag = Agent(agent_id=agent_uuid, tenant_id=tenant_uuid, name=b_info["agent_name"], status="active")
            session.add(ag)
            await session.commit()
            logger.info(f"Created synthetic Agent {agent_uuid} in Postgres")

    # 6. Step 4: Publish brain to Postgres compiled_brain_snapshots
    logger.info(f"Publishing SaaS employee brain for {agent_uuid}...")
    published = await publish_saas_employee_brain(
        str(agent_uuid),
        brief=b_info["brief"],
        language="te-IN",
        generation_config=gen_cfg,
        compiled_artifact=(compiled, script_result, variables),
    )
    snapshot = published.get("snapshot") or {}
    compiled_version = str(snapshot.get("compiled_version") or "1")
    logger.info(f"Published version {compiled_version} for agent {agent_uuid}")

    # 7. Compile capabilities & verify effective session prompt
    effective_prompt = await compile_agent_capabilities(compiled, str(agent_uuid))
    resolved_stack = resolve_stack(tier="medium", language="te-IN")

    brain_checksum = hashlib.sha256(compiled.encode("utf-8")).hexdigest()
    effective_prompt_checksum = hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest()

    # Verification: check Telugu pack and capability presence
    has_telugu_pack = "--- SPOKEN LANGUAGE (te-IN) ---" in effective_prompt
    has_capabilities = "--- CALL CAPABILITIES ---" in effective_prompt
    logger.info(f"Verification: has_telugu_pack={has_telugu_pack}, has_capabilities={has_capabilities}")

    agent_record = {
        "business_id": b_info["id"],
        "business_key": b_info["key"],
        "business_name": b_info["name"],
        "tenant_id": str(tenant_uuid),
        "agent_id": str(agent_uuid),
        "agent_name": script_result.agent_name or b_info["agent_name"],
        "role_summary": script_result.role_summary or b_info["role"],
        "selected_language": "te-IN",
        "resolved_stack": resolved_stack.to_safe_dict(),
        "original_brief": b_info["brief"],
        "clarification_answers": answered_log,
        "generated_business_script": script_result.agent_script,
        "compiled_brain_version": compiled_version,
        "compiled_brain_checksum": brain_checksum,
        "effective_prompt_checksum": effective_prompt_checksum,
        "has_telugu_pack": has_telugu_pack,
        "has_capabilities": has_capabilities,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save artifact files
    agent_dir = OUT_DIR / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_file = agent_dir / f"agent_{b_info['id']}_{b_info['key']}.json"
    agent_file.write_text(json.dumps(agent_record, indent=2, ensure_ascii=False), encoding="utf-8")
    
    script_file = agent_dir / f"agent_{b_info['id']}_script.txt"
    script_file.write_text(script_result.agent_script, encoding="utf-8")

    prompt_file = agent_dir / f"agent_{b_info['id']}_effective_prompt.txt"
    prompt_file.write_text(effective_prompt, encoding="utf-8")

    logger.info(f"Saved artifacts for Business {b_info['id']} to {agent_file}")
    return agent_record


async def main():
    await init_db()
    await load_tier_cache()
    results = []
    try:
        for b in BUSINESSES:
            res = await create_and_publish_agent(b)
            results.append(res)
        summary_file = OUT_DIR / "agents" / "agents_summary.json"
        summary_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Successfully created and published all {len(results)} agents!")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())

