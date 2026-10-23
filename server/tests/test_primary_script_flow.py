"""Primary Gemini script compilation, locale and editor API regressions; no live keys."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from server.brain.business_brain_store import business_brain_store
from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.semantic_validation import validate_sections
from server.prompts.agent_voice_rules import (
    LANGUAGE_LOCK, SPOKEN_PACKS, build_recording_disclosure_instruction, spoken_pack_for,
)
from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
from server.realtime.models import realtime_voice_llm_provider


def sections(script="--- AGENT IDENTITY ---\nYou are Meera, representing Example Support.\n\n--- CANONICAL OPENING ---\nSay once:\nHello, how can I help?"):
    return [
        {"section_id": "identity", "type": "identity_purpose", "title": "Identity & Purpose", "enabled": True, "raw_text": "Professional support agent.", "order": 10},
        {"section_id": "script", "type": "facts", "title": "Calling script", "enabled": True, "raw_text": script, "order": 20},
        {"section_id": "guardrails", "type": "guardrails", "title": "Guardrails", "enabled": True, "raw_text": "Never invent policies.", "order": 30},
    ]


@pytest.mark.parametrize("language", list(SPOKEN_PACKS))
def test_selected_locale_keeps_one_pack_and_all_business_content(language):
    body = "--- AGENT IDENTITY ---\nYou are Meera.\n\n--- COMPANY & OFFER ---\n" + ("Known product details. " * 1000) + "FINAL PRICE: INR 13750.\n\n--- FAQ & OBJECTIONS ---\nFinal FAQ: support closes at 18:15.\n\n--- CONVERSATION FLOW ---\nAsk the request first.\n\n--- INBOUND WORKFLOW ---\nConfirm resolution last."
    prompt = build_gemini_audio_session_instructions(assemble_unified_brain(language=language, script=body), language=language, direction="inbound", token_budget=500)
    assert prompt.count(LANGUAGE_LOCK[language]) == 1
    assert "FINAL PRICE: INR 13750." in prompt
    assert "Final FAQ: support closes at 18:15." in prompt
    assert "Confirm resolution last." in prompt
    assert "Ask the request first." in prompt
    assert "fifty lakhs" not in spoken_pack_for(language, core_only=True)


@pytest.mark.parametrize("language", list(SPOKEN_PACKS))
def test_disclosure_has_no_invented_consultation_or_repeated_example(language):
    policy = build_recording_disclosure_instruction(language=language)
    assert "consultation" not in policy
    assert "Got it!" not in policy
    if not language.startswith("en"):
        assert "This call may be recorded" not in policy
    assert '"Exact approved notice"' in build_recording_disclosure_instruction("Exact approved notice", language)


def test_changing_language_refreshes_old_runtime_footer_and_register():
    compiled = assemble_unified_brain(language="en-US", script="Approved facts", style="American English")
    runtime = build_gemini_audio_session_instructions(compiled, language="kn-IN", direction="inbound")
    assert "Language: en-US" not in runtime
    assert "American English" not in runtime
    assert LANGUAGE_LOCK["kn-IN"] in runtime


def test_legacy_preamble_and_authored_voice_examples_are_preserved():
    compiled = "Approved preamble: office opens at 08:45.\n\n--- COMPANY & OFFER ---\nSupport service.\n\n--- VOICE EXAMPLES ---\nUse this approved local phrasing."
    runtime = build_gemini_audio_session_instructions(compiled, language="te-IN", token_budget=100)
    assert runtime.count("Approved preamble: office opens at 08:45.") == 1
    assert "Use this approved local phrasing." in runtime


@pytest.mark.parametrize("model", [None, "", "invalid-model", "gemini-3.8-live"])
def test_explicit_gemini_stack_never_becomes_secondary(model):
    provider, selected = realtime_voice_llm_provider(stack_override={"llm": {"provider": "gemini", "model": model}})
    assert provider == "gemini"
    assert "live" in selected


@pytest.mark.asyncio
async def test_generation_failure_retries_only_selected_provider(monkeypatch):
    from server.brain import generation_runtime, agent_script_compiler as compiler
    from server.providers.base import LLMConfig
    adapter = SimpleNamespace(structured_completion=AsyncMock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (adapter, LLMConfig(provider="gemini", model="test-gemini")))
    result = await compiler._llm_generate_script("Known facts only", language="te-IN", budget_tokens=3500)
    assert result is None
    assert adapter.structured_completion.await_count == 2
    assert all(call.kwargs["config"].provider == "gemini" for call in adapter.structured_completion.await_args_list)


@pytest.mark.asyncio
async def test_generation_uses_selected_locale_and_inbound_direction(monkeypatch):
    from server.brain import generation_runtime, agent_script_compiler as compiler
    from server.providers.base import LLMConfig
    adapter = SimpleNamespace(structured_completion=AsyncMock(return_value={"agent_name": "Meera", "company_name": "Example Support"}))
    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (adapter, LLMConfig(provider="gemini", model="test-gemini")))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    await compiler._llm_interpret_brief("Support agent Meera", language="kn-IN", direction="inbound")
    system = adapter.structured_completion.await_args.kwargs["input_messages"][0]["content"][0]["text"]
    assert LANGUAGE_LOCK["kn-IN"] in system
    assert "The caller contacted you" in system


@pytest.mark.asyncio
async def test_long_brief_keeps_late_facts_and_policies_even_with_lossy_interpretation(monkeypatch):
    from server.brain import agent_script_compiler as compiler
    brief = "Create a support agent named Meera for Example Support. " + ("The standard inspection includes a written checklist. " * 15) + "The Chennai office closes at 18:15. Replacement part ZX42 is discontinued. Refund approval requires a manager. Do not sell extended warranties."
    interpretation = AsyncMock(return_value={"agent_name": "Meera", "company_name": "Example Support", "offer": "We offer inspections."})
    monkeypatch.setattr(compiler, "_llm_interpret_brief", interpretation)
    compiled, result, *_ = await compiler.compile_agent_from_brief(brief=brief, language="en-IN", direction="inbound")
    runtime = build_gemini_audio_session_instructions(compiled, language="en-IN", direction="inbound")
    for fact in ("Chennai office closes at 18:15", "part ZX42 is discontinued", "Refund approval requires a manager", "Do not sell extended warranties"):
        assert fact in result.agent_script
        assert fact in runtime


@pytest.mark.parametrize("tag", ["{{contact.name", "}}before{{", "{{ nested {{contact.name}} }}", "{{}}"])
def test_malformed_variables_block_publish_validation(tag):
    result = validate_sections(sections(tag))
    assert not result.ok
    assert any(issue.code == "malformed_variable" for issue in result.issues)


def test_natural_language_mix_and_valid_fallback_are_accepted():
    rows = sections("Hello {{contact.first_name | there}}")
    rows.append({"type": "faq", "enabled": True, "raw_text": "సరే, appointment details చెప్తాను."})
    result = validate_sections(rows)
    assert result.ok
    assert not any(issue.code == "script_mix" for issue in result.issues)


def test_legacy_enabled_voice_and_variable_metadata_never_enters_prompt():
    from server.brain.business_brain_store import assemble_raw_business_prompt
    rows = sections("Approved business fact") + [
        {"type": "custom", "title": title, "enabled": True, "raw_text": "INTERNAL CONFIG ONLY"}
        for title in ("saas_voice_config", "saas_script_variables", "Voice profile (console)", "Inbound routing prefs (console)")
    ]
    raw, _ = assemble_raw_business_prompt(rows)
    assert "Approved business fact" in raw
    assert "INTERNAL CONFIG ONLY" not in raw


@pytest.fixture
def client():
    import uuid
    from types import SimpleNamespace
    from server.app import app
    from server.auth.instructions_access import InstructionsAccess, require_instructions_access
    from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
    mock_access = InstructionsAccess(tenant_id=uuid.UUID("00000000-0000-4000-8000-000000000001"), role="administrator", developer=True)
    sub_principal = SimpleNamespace(
        tenant_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        email="test@example.com",
        role="customer_admin",
        is_admin=True,
        permissions=frozenset({"app.agents.write", "app.brain.write"}),
    )
    app.dependency_overrides[require_instructions_access] = lambda: mock_access
    app.dependency_overrides[require_subscriber_jwt_if_enabled] = lambda: sub_principal
    yield TestClient(app)
    app.dependency_overrides.pop(require_instructions_access, None)
    app.dependency_overrides.pop(require_subscriber_jwt_if_enabled, None)


def create_agent(client):
    response = client.post("/api/agents", json={"name": "Primary Script Test", "languages": ["en-IN"]})
    assert response.status_code == 200
    return response.json()["agent"]["agent_id"]


def test_review_does_not_mutate_draft_or_publish(client):
    agent_id = create_agent(client)
    url = f"/api/agents/{agent_id}/business-brain"
    before = client.get(url).json()
    response = client.post(url + "/preview", json={"sections": sections("New draft {{contact.first_name | there}}")})
    assert response.status_code == 200
    assert response.json()["ok"]
    assert response.json()["token_estimate"] > 0
    after = client.get(url).json()
    assert before == after


def test_review_requires_known_agent(client):
    assert client.post("/api/agents/no-such-agent/business-brain/preview", json={"sections": sections()}).status_code == 404


def test_preview_enforces_tenant_ownership(client, monkeypatch):
    import uuid
    from fastapi import HTTPException
    from server.auth.instructions_access import InstructionsAccess, require_instructions_access
    from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
    import server.routes.agents_business_brain as routes
    tenant_uuid = uuid.UUID("00000000-0000-4000-8000-000000000001")
    principal = InstructionsAccess(tenant_id=tenant_uuid, role="admin", developer=False)
    ownership = AsyncMock(side_effect=HTTPException(status_code=404, detail="Agent not found"))
    monkeypatch.setattr(routes, "subscriber_workspace_tenant_id", lambda _: tenant_uuid)
    monkeypatch.setattr(routes, "load_agent_for_tenant", ownership)
    client.app.dependency_overrides[require_instructions_access] = lambda: principal
    client.app.dependency_overrides[require_subscriber_jwt_if_enabled] = lambda: principal
    try:
        response = client.post("/api/agents/other-tenant-agent/business-brain/preview", json={"sections": sections()})
        assert response.status_code == 404
        ownership.assert_awaited_once_with("other-tenant-agent", tenant_uuid)
    finally:
        client.app.dependency_overrides.pop(require_subscriber_jwt_if_enabled, None)


def test_edited_identity_updates_hidden_runtime_tags(client):
    agent_id = create_agent(client)
    url = f"/api/agents/{agent_id}/business-brain"
    tagged = "--- ENTITY TAGS ---\n@agent_name: OldName\n@company_name: OldCompany\n@opening_line: Old greeting\n\n--- AGENT IDENTITY ---\nYou are OldName, representing OldCompany."
    initial = client.get(url).json()
    rev1 = initial["draft"]["revision"]
    assert client.put(url + "/draft", json={"sections": sections(tagged), "expected_revision": rev1}).status_code == 200
    after_first = client.get(url).json()
    rev2 = after_first["draft"]["revision"]
    assert client.put(url + "/draft", json={"sections": sections(), "expected_revision": rev2}).status_code == 200
    body = client.get(url).json()["draft"]["sections"]
    script = next(row["raw_text"] for row in body if row["title"] == "Calling script")
    assert "@agent_name: Meera" in script
    assert "@company_name: Example Support" in script
    assert "@opening_line: Hello, how can I help?" in script
    assert "OldName" not in script


def test_primary_web_call_resolves_template_fallback_without_imported_contact(client, monkeypatch):
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.call import call_context
    agent_id = create_agent(client)
    compiled = assemble_unified_brain(language="en-IN", script="Hello {{contact.first_name | there}}. Today is {{system.date}}.")
    monkeypatch.setattr(call_lifecycle_service, "_lock_compiled_brain", AsyncMock(return_value=("test-approved", compiled, "published")))
    started = client.post("/api/call/start", json={"sessionId": "primary-template-test", "agentId": agent_id,
        "channel": "browser", "stackOverride": {"pipeline": "realtime_voice", "voice_flow": "realtime_e2e", "llm": {"provider": "gemini", "model": "gemini-3.8-live"}}})
    assert started.status_code == 200, started.text
    assert started.json()["pipeline"] == "realtime_voice"
    context = call_context.get(started.json()["call_id"])
    assert "Hello there." in context.compiled_brain_text
    assert "{{" not in context.compiled_brain_text


@pytest.mark.asyncio
async def test_publish_preserves_authored_text_without_generation(monkeypatch):
    from server.brain.agent_service import agent_service
    import server.brain.business_prompt_optimizer as optimizer
    agent = await agent_service.create_agent(name="Preserve Authored Test")
    agent_id = agent["agent_id"]
    wording = "EXACT AUTHORED WORDING: Refund policy 7 days, price INR 13750."
    await business_brain_store.save_draft_sections(agent_id, sections(wording))
    llm = AsyncMock(side_effect=AssertionError("Publishing must not rewrite the script"))
    monkeypatch.setattr(optimizer, "_llm_compress_prompt", llm)
    snap = await compiled_brain_service.publish_agent_brain(agent_id)
    assert wording in snap["compiled_text"]
    assert snap["compiled_text"].count("--- STATIC OUTPUT RULES ---") == 1
    assert snap["compiled_text"].count("--- SPOKEN LANGUAGE (") == 1
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_recompile_keeps_published_content_and_does_not_promote_draft():
    from server.brain.agent_service import agent_service
    agent = await agent_service.create_agent(name="Approved Only Test")
    agent_id = agent["agent_id"]
    await business_brain_store.save_draft_sections(agent_id, sections("APPROVED BUSINESS FACT"))
    first = await compiled_brain_service.publish_agent_brain(agent_id)
    await business_brain_store.save_draft_sections(agent_id, sections("UNPUBLISHED BUSINESS FACT"))
    versions_before = await business_brain_store.get_versions(agent_id)
    rebuilt = await compiled_brain_service.compile_for_agent(agent_id)
    assert "APPROVED BUSINESS FACT" in rebuilt["compiled_text"]
    assert "UNPUBLISHED BUSINESS FACT" not in rebuilt["compiled_text"]
    assert rebuilt["business_version"] == first["business_version"]
    assert await business_brain_store.get_versions(agent_id) == versions_before


@pytest.mark.asyncio
async def test_legacy_assembly_recompile_keeps_approved_script():
    from server.brain.agent_service import agent_service
    from server.brain.business_brain_store import assemble_raw_business_prompt
    agent = await agent_service.create_agent(name="Legacy Approved Only Test")
    agent_id = agent["agent_id"]
    approved_sections = sections("APPROVED LEGACY FACT")
    await business_brain_store.save_draft_sections(agent_id, approved_sections)
    _, checksum = assemble_raw_business_prompt(approved_sections)
    await business_brain_store.save_published_version(agent_id,
        optimized_prompt=assemble_unified_brain(language="en-IN", script="APPROVED LEGACY FACT"),
        source_checksum=checksum, optimizer_report={})
    await business_brain_store.save_draft_sections(agent_id, sections("UNAPPROVED NEW FACT"))
    rebuilt = await compiled_brain_service.compile_for_agent(agent_id)
    assert "APPROVED LEGACY FACT" in rebuilt["compiled_text"]
    assert "UNAPPROVED NEW FACT" not in rebuilt["compiled_text"]
    assert rebuilt["compiled_text"].count("--- STATIC OUTPUT RULES ---") == 1
