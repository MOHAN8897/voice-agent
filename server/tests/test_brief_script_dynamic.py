"""Five brief→script scenarios: identity, offer, and opening must follow the brief."""
from __future__ import annotations

import pytest

from server.brain.agent_script_compiler import (
    compile_agent_from_brief,
    extract_agent_name_from_brief,
    extract_callee_name_from_brief,
    resolve_script_identity,
)

SCENARIOS = (
    {
        "key": "mohan_chandana_test",
        "language": "en-IN",
        "brief": (
            "my name is mohan i want you to talk like a friend and talk like u represent me "
            "i want to test the agent on my friend name is chandana i want her that this is a test call"
        ),
        "agent": "Mohan",
        "callee": "Chandana",
        "forbid": ("Priya", "Alex"),
        "need_script": ("Mohan", "Chandana", "test call", "friend"),
        "need_opening": ("Chandana", "Mohan", "test call"),
    },
    {
        "key": "priya_acme_sales",
        "language": "en-IN",
        "brief": (
            "Create an English sales agent named Priya for Acme Realty. "
            "Known listing: 2BHK plots near Hyderabad at 50 lakhs."
        ),
        "agent": "Priya",
        "company": "Acme Realty",
        "need_script": ("Priya", "Acme Realty", "50 lakhs"),
        "need_opening": ("Priya", "Acme"),
        "forbid": ("Mohan",),
    },
    {
        "key": "neha_inbound_support",
        "language": "en-IN",
        "brief": "inbound support at CityFiber. Agent name Neha. Help callers with fiber outages.",
        "agent": "Neha",
        "company": "CityFiber",
        "need_script": ("Neha", "CityFiber", "fiber"),
        "need_opening": ("Neha",),
    },
    {
        "key": "meera_education_fees",
        "language": "en-IN",
        "brief": (
            "Create an English education counsellor named Meera for Horizon Learning. "
            "Course fee is 15,000. Offer a trial class."
        ),
        "agent": "Meera",
        "company": "Horizon Learning",
        "need_script": ("Meera", "Horizon Learning", "15,000", "trial class"),
        "need_opening": ("Meera", "Horizon"),
        "forbid": ("Create an English education counsellor",),
    },
    {
        "key": "arun_colleague_invoice",
        "language": "en-IN",
        "brief": (
            "I am Arun. Call my colleague Suresh about the delayed invoice. "
            "Talk professionally as me and represent me. This is a follow-up, not a sales pitch."
        ),
        "agent": "Arun",
        "callee": "Suresh",
        "need_script": ("Arun", "Suresh", "invoice"),
        "need_opening": ("Arun", "Suresh"),
        "forbid": ("Priya", "Acme"),
    },
    {
        "key": "kailash_aditya_birla_insurance",
        "language": "en-IN",
        "brief": (
            "ok  u are bank person named kailash whose work is doing calsl realted to insurance "
            "for aditya birla insturance private limited talk with users as friendly as possible "
            "explain eveything in simple words and make them buy insurance policies"
        ),
        "agent": "Kailash",
        "company": "Aditya Birla",
        "forbid": ("Priya", "Alex", "u are bank", "calsl", "site visit", "whose work"),
        "need_script": (
            "Kailash",
            "Aditya Birla",
            "insurance",
            "simple words",
            "friendly",
        ),
        "need_opening": ("Kailash", "Aditya Birla"),
    },
)


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SCENARIOS, ids=[row["key"] for row in SCENARIOS])
async def test_brief_compiles_to_matching_script(spec: dict[str, object]) -> None:
    brief = str(spec["brief"])
    language = str(spec["language"])
    name, company, _work, opening = resolve_script_identity(brief, language=language)
    assert name == spec["agent"], f"{spec['key']}: agent {name!r}"
    if spec.get("company"):
        assert spec["company"] in company or company == spec["company"]
    if spec.get("callee"):
        assert extract_callee_name_from_brief(brief, agent_name=name) == spec["callee"]
    for token in spec.get("need_opening") or ():
        assert token.lower() in opening.lower(), f"{spec['key']} opening missing {token!r}: {opening}"
    for token in spec.get("forbid") or ():
        assert token.lower() not in opening.lower(), f"{spec['key']} opening has {token!r}"

    _compiled, result, *_ = await compile_agent_from_brief(
        brief=brief, language=language, use_llm=False
    )
    script = result.agent_script or ""
    assert result.agent_name == spec["agent"]
    for token in spec.get("need_script") or ():
        assert token.lower() in script.lower(), f"{spec['key']} script missing {token!r}\n{script}"
    for token in spec.get("forbid") or ():
        if str(token).lower() == str(spec.get("agent") or "").lower():
            continue
        assert str(token).lower() not in script.lower(), f"{spec['key']} script has {token!r}"


def test_mohan_is_speaker_not_invented_priya() -> None:
    brief = (
        "my name is mohan i want you to talk like a friend and talk like u represent me "
        "i want to test the agent on my friend name is chandana i want her that this is a test call"
    )
    assert extract_agent_name_from_brief(brief) == "Mohan"
    assert extract_callee_name_from_brief(brief, agent_name="Mohan") == "Chandana"
    name, company, work, opening = resolve_script_identity(brief, language="en-IN")
    assert name == "Mohan"
    assert company == ""
    assert "priya" not in opening.lower()
    assert "chandana" in opening.lower()
    assert "test call" in opening.lower()
    assert "my and talk" not in work.lower()


def test_kailash_insurance_brief_is_not_priya() -> None:
    from server.brain.agent_script_compiler import (
        extract_company_from_brief,
        extract_persona_from_brief,
        extract_voice_from_brief,
    )
    from server.prompts.conversation_policy import infer_agent_role

    brief = (
        "ok  u are bank person named kailash whose work is doing calsl realted to insurance "
        "for aditya birla insturance private limited talk with users as friendly as possible "
        "explain eveything in simple words and make them buy insurance policies"
    )
    assert extract_agent_name_from_brief(brief) == "Kailash"
    company = extract_company_from_brief(brief)
    assert "Aditya Birla" in company
    assert "Insurance" in company
    assert "bank representative" in extract_persona_from_brief(brief).lower()
    assert "simple words" in extract_voice_from_brief(brief).lower()
    assert infer_agent_role(brief) == "sales"
    name, company, _work, opening = resolve_script_identity(brief, language="en-IN")
    assert name == "Kailash"
    assert "priya" not in opening.lower()
    assert "kailash" in opening.lower()
    assert "aditya birla" in opening.lower()


@pytest.mark.asyncio
async def test_llm_interpret_fills_standard_four_sections(monkeypatch) -> None:
    from server.brain import agent_script_compiler as compiler

    brief = (
        "ok  u are bank person named kailash whose work is doing calsl realted to insurance "
        "for aditya birla insturance private limited talk with users as friendly as possible "
        "explain eveything in simple words and make them buy insurance policies"
    )

    async def fake_interpret(_brief: str, *, language: str = "en-IN"):
        return {
            "agent_name": "Kailash",
            "company_name": "Aditya Birla Insurance Private Limited",
            "persona": "a bank representative",
            "role": "sales",
            "offer": (
                "Aditya Birla Insurance Private Limited. Call customers about insurance. "
                "Explain policies in simple words and help them buy a policy."
            ),
            "voice": "Talk in a friendly way and use simple words",
            "opening_line": (
                "Hi, this is Kailash calling from Aditya Birla Insurance Private Limited. "
                "Do you have a moment?"
            ),
        }

    monkeypatch.setattr(compiler, "_llm_interpret_brief", fake_interpret)
    _compiled, result, *_ = await compiler.compile_agent_from_brief(
        brief=brief, language="en-IN", use_llm=False, interpret_brief=True
    )
    script = result.agent_script or ""
    assert result.agent_name == "Kailash"
    assert "You are Priya" not in script
    assert "You are Kailash" in script
    assert "Aditya Birla Insurance" in script
    assert "--- AGENT IDENTITY ---" in script
    assert "--- COMPANY & OFFER ---" in script
    assert "--- CANONICAL OPENING ---" in script
    assert "--- YOUR ROLE ON THIS CALL ---" in script
    assert "u are bank person" not in script.lower()
    assert "Explain policies in simple words" in script
    assert "site visit" not in script.lower()
    assert result.optimizer_model == "brief_interpret_v1"

