"""Conversation intelligence — role-aware policy, not a sales question tree."""
from __future__ import annotations

import pytest

from server.brain.agent_script_compiler import (
    _deterministic_script,
    ensure_script_identity_and_scope,
)
from server.prompts.conversation_policy import infer_agent_role, judge_turn, strict_live_fails
from server.brain.sections import STATIC_OUTPUT_RULES
from server.eval.behavior_scenarios import EVAL_BRIEFS, SCENARIOS
from server.prompts.agent_voice_rules import HUMAN_CALL_RULES, script_writer_system


def test_english_role_brief_does_not_garble_work_scope():
    from server.brain.agent_script_compiler import resolve_script_identity

    name, company, work, opening = resolve_script_identity(
        EVAL_BRIEFS["sales"]["brief"], language="en-IN"
    )
    assert name.lower() == "priya"
    assert "create an english" not in work.lower()
    assert "2BHK" in work or "fifty lakhs" in work.lower()
    assert "Hi, this is priya" in opening or "Priya" in opening
    assert infer_agent_role(EVAL_BRIEFS["sales"]["brief"]) == "sales"
    assert infer_agent_role(EVAL_BRIEFS["support"]["brief"]) == "support"
    assert infer_agent_role(EVAL_BRIEFS["recruitment"]["brief"]) == "recruitment"
    assert infer_agent_role("Help with failed payments and open a ticket") == "support"
    assert infer_agent_role("Screen candidates and schedule interviews") == "recruitment"
    assert infer_agent_role("Tuition for class 10 maths. Talk to parents.") == "education"


def test_support_script_does_not_sell():
    brief = EVAL_BRIEFS["support"]["brief"]
    script = _deterministic_script(
        brief,
        agent_name="Anu",
        company_name="Acme Billing",
        work_scope="billing tickets",
        opening_line="Hi, this is Anu",
        language="en-IN",
        role="support",
    )
    assert "Role: support" in script
    assert "Do not sell" in script
    assert "LIVE CALL GUIDE" in script
    assert "question tree" in script.lower() or "earn its place" in script.lower() or "checklist" in script.lower()
    assert "site visit" not in script.lower()


def test_recruitment_script_is_not_realty():
    brief = EVAL_BRIEFS["recruitment"]["brief"]
    script = _deterministic_script(
        brief,
        agent_name="Kavya",
        company_name="Northwind Labs",
        work_scope="backend engineer screening",
        opening_line="Hi, this is Kavya",
        language="en-IN",
        role="recruitment",
    )
    assert "Role: recruitment" in script
    assert "salary" in script.lower()
    assert "plot" not in script.lower()
    assert "apartment" not in script.lower()


def test_writer_forbids_question_tree():
    system = script_writer_system(language="en-IN", budget_tokens=3500)
    assert "question tree" in system.lower()
    assert "earn its place" in system.lower() or "answer before you qualify" in system.lower() or "ask-if-unknown" in system.lower()
    assert "do not assume property" in system.lower()
    assert "qualify budget, location, timeline" not in system.lower()
    assert "do not shorten" in system.lower() or "token savings" in system.lower()
    assert "target roughly" not in system.lower()


@pytest.mark.asyncio
async def test_thin_llm_script_uses_quality_floor(monkeypatch):
    import server.brain.agent_script_compiler as compiler

    async def thin(*args, **kwargs):
        return {
            "agent_script": (
                "--- VOICE STYLE ---\nBe brief.\n\n"
                "--- CONVERSATION FLOW ---\nAsk one question.\n"
            ),
            "agent_name": "Karthik",
            "company_name": "DriveRight Auto Care",
            "role": "sales",
            "role_summary": "sell service packages",
            "key_facts": ["basic service three thousand five hundred"],
        }

    monkeypatch.setattr(compiler, "_llm_generate_script", thin)
    _compiled, result, *_ = await compiler.compile_agent_from_brief(
        brief=(
            "Create an English sales counselor named Karthik for DriveRight Auto Care in Hyderabad. "
            "Sell periodic car service packages. Basic periodic service is three thousand five hundred rupees."
        ),
        language="en-IN",
        budget_tokens=6000,
        use_llm=True,
    )
    assert "LIVE CALL GUIDE" in result.agent_script
    assert "OBJECTION HANDLING" in result.agent_script
    assert "Source facts and duties" in result.agent_script or "WORK SCOPE" in result.agent_script
    assert result.optimizer_model in {
        "legacy_deterministic_quality_floor_v1",
        "legacy_deterministic_validation_fallback_v1",
        "legacy_deterministic_v1",
    }


def test_agent_script_schema_is_valid_for_openai_strict_mode():
    from server.brain.agent_script_compiler import AGENT_SCRIPT_SCHEMA

    assert set(AGENT_SCRIPT_SCHEMA["required"]) == set(AGENT_SCRIPT_SCHEMA["properties"])


@pytest.mark.asyncio
async def test_oversized_generated_script_falls_back_instead_of_failing(monkeypatch):
    import server.brain.agent_script_compiler as compiler

    async def oversized(*args, **kwargs):
        body = (
            "--- VOICE STYLE ---\nBe clear.\n\n"
            "--- CONVERSATION FLOW ---\nAnswer first.\n\n"
            "--- OBJECTION HANDLING ---\nAcknowledge concerns.\n\n"
            "--- GUARDRAILS ---\nNever invent facts.\n\n"
            "--- CLOSING ---\nThank them and close.\n\n"
            + ("oversized policy sentence. " * 12000)
        )
        return {
            "agent_script": body,
            "agent_name": "Nisha",
            "company_name": "",
            "role": "information",
            "role_summary": "library hours",
            "key_facts": [],
        }

    monkeypatch.setattr(compiler, "_llm_generate_script", oversized)
    compiled, result, *_ = await compiler.compile_agent_from_brief(
        brief="Answer City Library opening-hours questions. Agent name Nisha.",
        language="en-IN",
        use_llm=True,
    )
    assert result.optimizer_model == "simple_business_budget_fallback_v1"
    assert "BUSINESS KNOWLEDGE" in result.agent_script or "COMPANY & OFFER" in result.agent_script
    assert compiler.estimate_tokens(compiled) <= compiler.BUDGET_MAX_TOKENS


def test_static_and_human_rules_are_role_agnostic():
    blob = (STATIC_OUTPUT_RULES + "\n" + HUMAN_CALL_RULES).lower()
    assert "checklist" in blob or "question tree" in blob or "ask-if-unknown" in blob
    assert "overrides script defaults" in blob
    assert "don't call" in blob or "dont call" in blob.replace("'", "")
    assert "whatsapp" in blob
    assert "not a hangup" in blob or "do not hang up" in blob
    assert "must not sell" in blob or "do not sell" in blob
    assert "earn its place" in blob or "never re-ask" in blob or "natural sales" in blob
    assert "plot vs apartment" not in blob
    assert "never say goodbye" in blob
    assert "sarcasm" in blob
    assert "executed tool" in blob
    assert "correct" in blob


def test_judge_catches_qualification_and_hangup():
    assert judge_turn(
        user="How much does it cost?",
        assistant="Before I tell you, what's your budget?",
        expect=("no_qualify", "no_question"),
    )
    assert not judge_turn(
        user="How much does it cost?",
        assistant="The known listing is fifty lakhs.",
        expect=("no_qualify", "no_question"),
    )
    assert judge_turn(
        user="Don't call again.",
        assistant="Okay, thanks.",
        end_call={"should_end": False},
        expect=("hangup",),
    )
    assert not judge_turn(
        user="Don't call again.",
        assistant="Thank you for your time. Goodbye.",
        end_call={"should_end": True, "reason": "goodbye"},
        expect=("hangup", "no_question", "short"),
    )
    assert judge_turn(
        user="Wait, how much?",
        assistant="As I was saying, we also have amenities.",
        expect=("no_old_script",),
    )
    assert judge_turn(
        user="Please slow down, that was fast.",
        assistant="Calm down and repeat.",
        expect=("no_calm_down",),
    )
    assert judge_turn(
        user="This is taking too long. I'm getting frustrated.",
        assistant="Sorry. The two-bedroom apartments start from fifty lakhs, and I can arrange a site visit.",
        expect=("short", "no_qualify"),
    )
    assert judge_turn(
        user="What's the salary?",
        assistant="The salary is twelve lakhs per year plus joining bonus.",
        expect=("no_hangup",),
    )
    assert judge_turn(
        user="hmm",
        assistant="Would you like a site visit?",
        expect=("no_are_you_there",),
    )
    assert strict_live_fails(
        user="Don't call me again.",
        assistant="Okay, thanks.",
        end_call={"should_end": False},
        expect=("hangup",),
    )
    assert "hung up on frustration" in strict_live_fails(
        user="I've already explained this twice.",
        assistant="Sorry. Goodbye.",
        end_call={"should_end": True, "reason": "goal_complete"},
    )
    assert "invented a prior opt-out or previous call" in strict_live_fails(
        user="How much are the fees?",
        assistant="Since you asked not to be called again, I won't continue.",
        end_call={"should_end": False},
        expect=("no_question",),
    )
    assert "said goodbye without hanging up" in judge_turn(
        user="yeah just tell me the price quickly",
        assistant="Two-bedrooms start from fifty lakhs. Thank you for your time. Goodbye.",
        end_call={"should_end": False},
        expect=("no_question",),
    )
    assert not judge_turn(
        user="Email me later.",
        assistant="I'll email you the details. Thanks.",
        end_call={"should_end": False},
        expect=("no_question", "short"),
    )
    assert "pitched through sarcasm" in judge_turn(
        user="fifty lakhs for that? Sure, and I own the moon.",
        assistant="I can arrange a site visit this weekend.",
        end_call={"should_end": False},
        expect=("no_question",),
    )


ROLE_COLLISIONS = [
    ("Talk to parents about our classes", "education"),
    ("Help people learn about our course", "education"),
    ("Call candidates about opportunities", "recruitment"),
    ("Contact customers regarding their account", "support"),
    ("Reach out to people who showed interest", "follow_up"),
    ("Talk to existing customers about an issue", "support"),
    ("Call people and explain our service", "information"),
    ("Help customers choose the right plan", "sales"),
    ("Contact applicants about next steps", "recruitment"),
    ("Call leads who requested information", "information"),
    ("Sell our course to parents", "sales"),
    ("Help customers choose the right plan and also fix billing tickets", "support"),
    ("Explain our 2BHK listing; only inform unless they ask to book", "information"),
    ("Screen candidates and book interview slots", "recruitment"),
    ("Fix account issues and keep customers from cancelling", "support"),
    ("Follow up on leads who asked about apartments", "follow_up"),
    ("Answer library questions and book reading-room slots", "appointment"),
    ("Golf course villas for sale, agent named Ravi", "sales"),
    ("Resume your subscription after a failed payment ticket", "support"),
    ("Interview the customer about which plot they want", "sales"),
    ("Create an English sales agent named Priya for Acme Realty", "sales"),
    ("Batch of 1000 square feet apartments at 50 lakhs", "sales"),
    ("Book dentist slots at Smile Clinic", "appointment"),
    ("FAQ agent for city library hours. Do not sell.", "information"),
    ("Checking in with people who requested a callback last week", "follow_up"),
    ("Help customers understand an electric car and arrange test drives", "sales"),
    ("Support SaaS users with login and billing problems. Do not upsell.", "support"),
    (
        "Call people and explain our 2BHK apartments from fifty lakhs. Agent name Swetha. Book visits.",
        "sales",
    ),
    (
        "Follow up with people who requested a callback. Do not restart a sales pitch.",
        "follow_up",
    ),
    ("After-sales support for billing tickets", "support"),
    (
        "Sell periodic car service packages and AMC for DriveRight Auto Care car service in Hyderabad.",
        "sales",
    ),
    (
        "Create an English service agent named Ravi for AutoCare Motors car service center. "
        "Book service requests. Do not sell cars.",
        "support",
    ),
]


def test_role_detection_handles_collisions_and_unlabeled_briefs():
    for brief, expected in ROLE_COLLISIONS:
        assert infer_agent_role(brief) == expected, f"{brief!r} -> {infer_agent_role(brief)} expected {expected}"


def test_english_compile_style_is_not_telugu():
    from server.brain.agent_script_compiler import _assemble_brain, _deterministic_script, resolve_script_identity
    from server.prompts.conversation_policy import infer_agent_role

    brief = "Talk to parents about our classes. Agent name Meera."
    name, company, work, opening = resolve_script_identity(brief, language="en-IN")
    assert name.lower() == "meera"
    script = _deterministic_script(
        brief,
        agent_name=name,
        company_name=company,
        work_scope=work,
        opening_line=opening,
        language="en-IN",
        role=infer_agent_role(brief),
    )
    brain = _assemble_brain(script=script, language="en-IN", style=None)
    assert "spoken Telugu" not in brain
    assert "spoken Indian English" in brain
    assert "budget, location, or timeline" not in script
    assert "Role: education" in script
    assert "Hi, this is Meera" in opening
    assert "Talk to parents" not in opening
    from server.brain.agent_script_compiler import work_scope_from_brief

    work2 = work_scope_from_brief(
        "Talk to parents about our class 10 maths batches. Agent name Meera. "
        "Known fee is eight thousand a month. Never invent exam results.",
        "",
    )
    assert "eight thousand" in work2.lower()
    assert "meera" not in work2.lower()


def test_work_scope_strips_guardrail_sentences():
    from server.brain.agent_script_compiler import work_scope_from_brief

    follow = work_scope_from_brief(
        "Follow up with people who requested a callback last week about a pending application. "
        "Agent name Dev. Do not restart a sales pitch.",
        "",
    )
    assert "callback" in follow.lower()
    assert "sales pitch" not in follow.lower()
    assert "do not restart" not in follow.lower()

    appl = work_scope_from_brief(
        "Contact applicants about next steps for the backend engineer role. "
        "Agent name Kavya. Salary is not in this brief.",
        "",
    )
    assert "backend engineer" in appl.lower()
    assert "salary is not" not in appl.lower()

    appt = work_scope_from_brief(
        "Book dentist slots at Smile Clinic. Agent name Ravi. "
        "Weekday hours ten AM to six PM. Do not sell whitening packages.",
        "",
    )
    assert "dentist" in appt.lower()
    assert "do not sell" not in appt.lower()
    assert "whitening" not in appt.lower()


def test_llm_role_cannot_override_confident_keyword_score():
    assert infer_agent_role("Sell our course to parents", llm_role="education") == "sales"
    assert infer_agent_role("Talk to parents about our classes", llm_role="sales") == "education"
    assert infer_agent_role("Resume your subscription after a failed payment ticket", llm_role="recruitment") == "support"


def test_agent_name_starting_with_is_is_not_truncated():
    from server.brain.agent_script_compiler import extract_agent_name_from_brief, work_scope_from_brief

    brief = "Support SaaS users with login issues. Agent name Ishita. Do not upsell."
    assert extract_agent_name_from_brief(brief) == "Ishita"
    assert "ishita" not in work_scope_from_brief(brief, "").lower()
    assert "do not upsell" not in work_scope_from_brief(brief, "").lower()

    no_tools = work_scope_from_brief(
        "Help with failed payments. Agent name Anu. "
        "No email, ticketing, refund, or account-change tools are connected.",
        "",
    )
    assert "failed payments" in no_tools.lower()
    assert "tools are connected" not in no_tools.lower()
    assert extract_agent_name_from_brief("Agent name: John Smith. Call leads.") == "John Smith"
    assert extract_agent_name_from_brief("Agent name: దీప్తి. Parents కి call చేయండి.") == "దీప్తి"


def test_judge_catches_unperformed_action_claims():
    assert "claimed an unavailable or unperformed action" in judge_turn(
        user="Email it to me.",
        assistant="I've emailed the brochure.",
        expect=("no_action_claim",),
    )
    assert not judge_turn(
        user="Email it to me.",
        assistant="I can't send it directly.",
        expect=("no_action_claim",),
    )


def test_english_ignores_stored_telugu_style():
    from server.brain.agent_script_compiler import _assemble_brain
    from server.prompts.voice_defaults import style_for_language

    assert "Telugu" not in style_for_language("very brief, 1-2 sentences, spoken Telugu", "en-IN")
    brain = _assemble_brain(
        script="x",
        language="en-IN",
        style="very brief, 1-2 sentences, spoken Telugu",
    )
    assert "spoken Telugu" not in brain
    assert "spoken Indian English" in brain


def test_native_english_brain_does_not_use_indian_register():
    from server.brain.agent_script_compiler import _assemble_brain
    from server.prompts.voice_defaults import style_for_language

    assert "Indian English" not in style_for_language(
        "warm, brief, 1-2 sentences, spoken Indian English like a person on a phone",
        "en-US",
    )
    brain = _assemble_brain(
        script="x",
        language="en-US",
        style="warm, brief, 1-2 sentences, spoken Indian English like a person on a phone",
    )
    assert "spoken Indian English" not in brain
    assert "US and UK" in brain or "en-US" in brain
    assert "Speak natural Tanglish" not in brain


def test_language_contract_is_last_in_compiled_brain():
    from server.brain.agent_script_compiler import _assemble_brain

    te = _assemble_brain(script="x", language="te-IN", style=None)
    assert "Telugu Unicode" in te or "Tanglish" in te
    assert "Every reply must stay in Telugu" in te or "Telugu/Tanglish" in te
    assert te.rstrip().endswith(
        "A refusal or off-scope redirect stands alone; never append business facts or a pitch."
    )


def test_scenarios_cover_multiple_roles():
    roles = {s["role"] for s in SCENARIOS}
    assert {"sales", "support", "recruitment"} <= roles
    assert all("expect" in s and "intent" in s for s in SCENARIOS)


def test_checklist_rewrite_still_works():
    raw = (
        "--- CONVERSATION FLOW ---\n"
        "Ask budget, location, and timeline one at a time.\n\n"
        "--- GUARDRAILS ---\nNever invent prices.\n"
    )
    out = ensure_script_identity_and_scope(
        raw,
        agent_name="Priya",
        company_name="Acme",
        work_scope="selling plots",
        opening_line="Hi",
        language="en-IN",
        role="sales",
    )
    assert "one at a time" not in out.lower()
    assert "NATURAL SALES PROGRESSION" in out
    assert "never re-ask" in out.lower()
    assert "Lead conversion" in out or "qualified lead" in out.lower() or "human salesperson" in out.lower()
    assert "Role: sales" in out


def test_step_tree_flow_always_replaced():
    raw = (
        "--- CONVERSATION FLOW ---\n"
        "Step 1 greet. Step 2 ask quantity. Step 3 ask budget. Step 4 close.\n\n"
        "--- GUARDRAILS ---\nNever invent.\n"
    )
    out = ensure_script_identity_and_scope(
        raw,
        agent_name="Kavya",
        company_name="PenMart",
        work_scope="selling pens",
        opening_line="Hi",
        language="en-IN",
        role="sales",
    )
    assert "step 2" not in out.lower()
    assert "NATURAL SALES PROGRESSION" in out or "never re-ask" in out.lower() or "question tree" in out.lower()
    assert "Step 1 greet" not in out


def test_deterministic_script_does_not_reinject_raw_guardrails():
    from server.brain.agent_script_compiler import _deterministic_script, work_scope_from_brief

    brief = (
        "Follow up on a pending application. Agent name Dev. "
        "Do not restart a sales pitch. Never invent availability."
    )
    work = work_scope_from_brief(brief, "")
    script = _deterministic_script(
        brief,
        agent_name="Dev",
        company_name="",
        work_scope=work,
        opening_line="Hi, this is Dev.",
        language="en-IN",
        role="follow_up",
    )
    source = script.split("Source facts and duties:", 1)[1]
    assert "pending application" in source.lower()
    assert "do not restart a sales pitch" not in source.lower()
    assert "never invent availability" not in source.lower()
    assert "executed tool" in script.lower()
