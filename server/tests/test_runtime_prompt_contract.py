"""Cross-provider policy, locale refresh and lossless legacy compilation contracts."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.agent.brain_prompt_composer import PromptBudgetExceeded, estimate_tokens
from server.brain.compiled_brain_artifact import (
    assemble_unified_brain,
    build_artifact,
    refresh_platform_sections,
)
from server.brain.sections import PLATFORM_PRIVACY_IDENTITY_RULES
from server.call.call_end_policy import CLOSING_TOOL_DESCRIPTION, default_call_end_policy
from server.prompts.agent_voice_rules import (
    CALL_END_FAREWELLS,
    SPOKEN_PACKS,
    build_recording_disclosure_instruction,
    normalize_compile_language,
    spoken_pack_for,
)
from server.realtime.hangup_tools import REQUEST_END_CALL_TOOL
from server.realtime.models import END_CALL_TOOL
from server.realtime.voice_instructions import build_realtime_voice_instructions


@pytest.mark.parametrize("locale", tuple(SPOKEN_PACKS))
@pytest.mark.parametrize("model", ["gemini-3.8-live", "gpt-realtime-2.1-mini", "composed"])
@pytest.mark.parametrize("unified", [True, False])
def test_minimal_business_script_cannot_drop_platform_privacy(locale, model, unified):
    brain = assemble_unified_brain(language=locale, script="Answer service questions.")
    if not unified:
        brain = "Answer service questions."
    if model == "composed":
        from server.services.composed_voice_session import composed_system_prompt

        ctx = SimpleNamespace(
            compiled_brain_text=brain, compiled_brain_version="test-v1", selected_language=locale,
        )
        prompt = composed_system_prompt(ctx)
    else:
        prompt = build_realtime_voice_instructions(brain, model=model, language=locale, direction="outbound")
    assert PLATFORM_PRIVACY_IDENTITY_RULES in prompt
    assert prompt.count(PLATFORM_PRIVACY_IDENTITY_RULES) == 1
    assert "Never say you are an AI" not in prompt


@pytest.mark.parametrize("locale", tuple(SPOKEN_PACKS))
def test_language_refresh_updates_farewell_disclosure_and_preserves_allowlist(locale):
    source = assemble_unified_brain(
        language="te-IN", script="Answer service questions.",
        call_end_policy={"allowedReasons": ["goodbye", "firm_refusal"]},
        platform_call_rules=build_recording_disclosure_instruction(language="te-IN"),
    )
    refreshed = refresh_platform_sections(source, locale)
    assert CALL_END_FAREWELLS[locale] in refreshed
    assert "Allowed close reasons for this agent: goodbye, firm_refusal." in refreshed
    assert build_recording_disclosure_instruction(language=locale).strip() in refreshed
    if locale != "te-IN":
        assert CALL_END_FAREWELLS["te-IN"] not in refreshed
        assert build_recording_disclosure_instruction(language="te-IN").strip() not in refreshed


@pytest.mark.parametrize("field", ["farewell", "disclosure"])
def test_custom_exact_locale_text_requires_review_before_language_change(field):
    source = assemble_unified_brain(
        language="en-IN", script="Answer service questions.",
        call_end_policy={"farewell": "Acme wishes you a good day."} if field == "farewell" else None,
        platform_call_rules=build_recording_disclosure_instruction(
            disclosure_text="Custom approved recording notice.", language="en-IN",
        ) if field == "disclosure" else "",
    )
    assert "Custom" in source or "Acme wishes" in source
    assert refresh_platform_sections(source, "en-IN")
    with pytest.raises(ValueError, match="must be reviewed"):
        refresh_platform_sections(source, "kn-IN")


def test_same_language_refresh_preserves_custom_farewell():
    source = assemble_unified_brain(
        language="en-IN", script="Support.", call_end_policy={"farewell": "Thanks from Acme. Goodbye."},
    )
    assert "Thanks from Acme. Goodbye." in refresh_platform_sections(source, "en-IN")


def test_both_hangup_aliases_share_one_runtime_closing_contract():
    assert END_CALL_TOOL["description"] == REQUEST_END_CALL_TOOL["description"] == CLOSING_TOOL_DESCRIPTION
    assert "immediately when the farewell playback" in CLOSING_TOOL_DESCRIPTION
    assert "when that workflow applies and is permitted" in CLOSING_TOOL_DESCRIPTION
    assert "only if they stay silent" not in CLOSING_TOOL_DESCRIPTION


@pytest.mark.parametrize("model", ["gemini-3.8-live", "gpt-realtime-2.1-mini"])
@pytest.mark.parametrize("unified", [True, False])
def test_forbidden_contact_and_callback_never_receive_unconditional_runtime_defaults(model, unified):
    script = "No callbacks. Never ask for a name or contact details. Answer product questions only."
    brain = assemble_unified_brain(language="en-IN", script=script) if unified else script
    prompt = build_realtime_voice_instructions(brain, model=model, language="en-IN", direction="outbound")
    assert script in prompt
    for obsolete_directive in (
        "Busy: one callback offer, stay on the line.",
        "If they are busy: one callback offer, no pitch.",
        "Ask an unknown preferred name at a natural pause after consent.",
        "Ask their preferred name once after they agree to speak, if unknown.",
        "For a callback they still want, collect only missing name/phone/day.",
    ):
        assert obsolete_directive not in prompt


@pytest.mark.parametrize("locale", tuple(SPOKEN_PACKS))
def test_contact_number_refusal_examples_do_not_promise_unavailable_followup(locale):
    from server.prompts.agent_voice_rules import PHONE_ASK_FALLBACK

    # Locale refusal examples contain only the refusal; a permitted next step
    # is supplied by the business workflow rather than this fallback sentence.
    assert " — " not in PHONE_ASK_FALLBACK[locale]
    assert "share yours" not in PHONE_ASK_FALLBACK[locale]
    assert "If you share yours" not in PHONE_ASK_FALLBACK[locale]


@pytest.mark.parametrize("model", ["gemini-3.8-live", "gpt-realtime-2.1-mini"])
def test_conflicting_runtime_language_fails_closed(model):
    from server.services.pstn_stack import PstnStackValidationError

    brain = assemble_unified_brain(language="en-IN", script="Speak only Hindi.")
    with pytest.raises(PstnStackValidationError, match="Brain language validation failed"):
        build_realtime_voice_instructions(brain, model=model, language="en-IN")


@pytest.mark.parametrize("bad_locale", ["ja-JP", "unknown", "xx-XX"])
def test_explicit_unsupported_locale_is_never_silently_coerced(bad_locale):
    with pytest.raises(ValueError, match="Unsupported language locale"):
        normalize_compile_language(bad_locale)


def test_locale_aliases_and_unspecified_default_remain_supported():
    assert normalize_compile_language(None) == normalize_compile_language("") == normalize_compile_language("  ") == "te-IN"
    assert normalize_compile_language("kn_in") == "kn-IN"


@pytest.mark.asyncio
async def test_legacy_optimizer_keeps_every_fact_without_trusting_lossy_model(monkeypatch):
    from server.brain import business_prompt_optimizer as optimizer

    lossy_model = AsyncMock(return_value={"optimized_prompt": "We sell products."})
    monkeypatch.setattr(optimizer, "_llm_compress_prompt", lossy_model)
    business = "\n".join(f"Variant {n} costs INR {100+n} per box." for n in range(20))
    business += "\nSTRICT_RETURN_WINDOW_23_DAYS."
    result = await optimizer.optimize_session_dual_prompt(
        behaviour="Answer current questions first.", business=business,
        raw_assembled=business, source_checksum="source", budget_tokens=1500,
    )
    assert business in result.optimized_business_prompt
    assert result.optimizer_model == "source_preserving_v1"
    lossy_model.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_compile_preserves_late_policy_or_returns_budget_error():
    from server.brain.session_brain_compiler import compile_session_brain

    business = "\n".join(f"Variant {n} costs INR {100+n} per box." for n in range(20))
    business += "\nSTRICT_RETURN_WINDOW_23_DAYS."
    compiled, report, *_ = await compile_session_brain(
        behaviour="Answer questions.", business=business, language="en-IN", budget_tokens=10000,
    )
    assert business in compiled
    assert "Variant 19 costs INR 119 per box." in compiled
    assert "STRICT_RETURN_WINDOW_23_DAYS" in report.optimized_business_prompt
    assert default_call_end_policy("en-IN")["farewell"] in compiled
    with pytest.raises(PromptBudgetExceeded):
        await compile_session_brain(
            behaviour="Answer questions.", business=business, language="en-IN", budget_tokens=1500,
        )


def test_artifact_reports_actual_lean_pack_and_platform_overhead():
    artifact = build_artifact(language="kn-IN", script="Equipment check costs INR 500.")
    estimates = artifact.section_token_estimates
    assert estimates["language_pack"] == estimate_tokens(spoken_pack_for("kn-IN", include_brevity=False, core_only=True))
    assert estimates["platform_overhead"] + estimates["business_script"] == estimates["total"]
