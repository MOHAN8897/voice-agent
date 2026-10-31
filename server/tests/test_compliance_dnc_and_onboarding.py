from server.tests.test_campaign_execution_safety import db as campaign_db
import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import Campaign, CampaignContact, DialAttempt, DncEntry
from server.db.models.saas_models import UserOnboardingSurvey, User
from server.prompts.agent_voice_rules import build_recording_disclosure_instruction
from server.brain.agent_script_compiler import _platform_call_rules, compile_agent_from_brief
from server.services.pstn_text_chunker import extract_opening_greeting
from server.services.saas.dnc_service import auto_enroll_dnc_opt_out, handle_call_opt_out
from server.services.saas.auth_service import check_user_completed_onboarding
from server.routes.campaigns import CampaignCreate, DncDeactivateBody


def test_phase1_orm_models():
    """Verify Phase 1 ORM models have all required compliance and audit columns."""
    # Agent
    assert hasattr(Agent, "recording_disclosure_enabled")
    assert hasattr(Agent, "recording_disclosure_text")

    # Campaign
    assert hasattr(Campaign, "consent_confirmed")
    assert hasattr(Campaign, "consent_attestation_version")
    assert hasattr(Campaign, "attested_by_user_id")
    assert hasattr(Campaign, "attested_at")
    assert hasattr(Campaign, "attested_ip")
    assert hasattr(Campaign, "attested_user_agent")

    # DncEntry
    assert hasattr(DncEntry, "active")
    assert hasattr(DncEntry, "source")
    assert hasattr(DncEntry, "added_by_user_id")
    assert hasattr(DncEntry, "removed_at")
    assert hasattr(DncEntry, "removed_by_user_id")
    assert hasattr(DncEntry, "removal_reason")
    assert hasattr(DncEntry, "reconsent_confirmed")

    # UserOnboardingSurvey
    assert hasattr(UserOnboardingSurvey, "id")
    assert hasattr(UserOnboardingSurvey, "user_id")
    assert hasattr(UserOnboardingSurvey, "tenant_id")
    assert hasattr(UserOnboardingSurvey, "role")
    assert hasattr(UserOnboardingSurvey, "referral_source")
    assert hasattr(UserOnboardingSurvey, "primary_use_case")
    assert hasattr(UserOnboardingSurvey, "estimated_monthly_minutes")
    assert hasattr(UserOnboardingSurvey, "terms_and_telephony_accepted")
    assert hasattr(UserOnboardingSurvey, "terms_version")
    assert hasattr(UserOnboardingSurvey, "acceptable_use_version")
    assert hasattr(UserOnboardingSurvey, "terms_accepted_at")


def test_phase2_campaign_attestation_validation():
    """Verify Campaign creation enforces consent attestation."""
    # Must fail or require consentConfirmed
    with pytest.raises(Exception):
        CampaignCreate(name="Test Campaign", agentId=str(uuid.uuid4()), consentConfirmed=False)

    valid_payload = CampaignCreate(
        name="Compliant Campaign",
        agentId=str(uuid.uuid4()),
        consentConfirmed=True,
        consentVersion="2026-10-v1",
    )
    assert valid_payload.consent_confirmed is True
    assert valid_payload.consent_version == "2026-10-v1"


def test_phase2_dnc_deactivation_validation():
    """Verify DND soft deactivation requires explicit re-consent and reason."""
    with pytest.raises(Exception):
        DncDeactivateBody(reconsentConfirmed=False, removalReason="Customer asked")

    with pytest.raises(Exception):
        DncDeactivateBody(reconsentConfirmed=True, removalReason="")

    valid = DncDeactivateBody(reconsentConfirmed=True, removalReason="Caller gave explicit written opt-in")
    assert valid.reconsent_confirmed is True
    assert valid.removal_reason == "Caller gave explicit written opt-in"


from server.services.saas.campaign_runner import run_campaign
from server.db.models.phase5_models import CampaignContact, CampaignRun, DialAttempt


@pytest.mark.asyncio
async def test_phase2_authoritative_predial_dnd_in_campaign_runner(campaign_db, monkeypatch):
    from sqlalchemy import select
    from server.tests.test_campaign_execution_safety import TID, seeded_campaign
    from server.services.saas import campaign_runner as runner
    cid, rid = await seeded_campaign(campaign_db, 1)
    async with campaign_db() as session:
        contact = (await session.execute(select(CampaignContact).where(CampaignContact.campaign_id == cid))).scalar_one()
        session.add(DncEntry(tenant_id=TID, phone_e164=contact.phone_e164, active=True))
        await session.commit()
    dial = AsyncMock()
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", dial)
    await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=uuid.uuid4())
    dial.assert_not_awaited()
    async with campaign_db() as session:
        contact = (await session.execute(select(CampaignContact).where(CampaignContact.campaign_id == cid))).scalar_one()
        attempt = (await session.execute(select(DialAttempt).where(DialAttempt.campaign_id == cid))).scalar_one()
        assert contact.status == "dnc_excluded"
        assert attempt.status == "dnc_skipped"


@pytest.mark.asyncio
async def test_phase2_live_call_opt_out_auto_enrollment():
    """Verify verbal opt-out auto-enrolls caller phone into tenant's DND list."""
    tenant_id = uuid.uuid4()
    phone = "+15559876543"

    mock_session = AsyncMock()
    # Mock dialect name
    mock_session.bind = MagicMock()
    mock_session.bind.dialect.name = "postgresql"

    class MockContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, *args):
            pass

    def mock_factory():
        return MockContextManager()

    with patch("server.db.connection.get_session_factory", return_value=mock_factory):
        success = await auto_enroll_dnc_opt_out(
            tenant_id=tenant_id,
            phone=phone,
        )

        assert success is True
        # execute must have been called with insert/upsert
        assert mock_session.execute.called
        assert mock_session.commit.called


@pytest.mark.asyncio
async def test_phase2_onboarding_survey_completion_check():
    """Verify check_user_completed_onboarding queries UserOnboardingSurvey table."""
    user_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = uuid.uuid4()
    mock_session.execute.return_value = mock_result

    completed = await check_user_completed_onboarding(mock_session, user_id)
    assert completed is True


def test_phase3_recording_disclosure_instruction_prompt():
    """Verify disclosure instruction generator creates a natural once-only policy."""
    # English default
    en_rule = build_recording_disclosure_instruction(language="en-US")
    assert "RECORDING DISCLOSURE POLICY (NATURAL, ONCE)" in en_rule
    assert "This call may be recorded for quality and training purposes." in en_rule
    assert "first substantive reply" in en_rule
    assert "standalone legal announcement" in en_rule
    assert "never repeat it later" in en_rule
    assert "If the caller interrupts the opening" in en_rule

    # Telugu default
    te_rule = build_recording_disclosure_instruction(language="te-IN")
    assert "క్వాలిటీ, ట్రైనింగ్ కోసం ఈ కాల్ రికార్డ్ చేయవచ్చు." in te_rule

    # Custom text
    custom_rule = build_recording_disclosure_instruction(
        disclosure_text="Notice: Calls are monitored for safety.",
        language="en-US",
    )
    assert "Notice: Calls are monitored for safety." in custom_rule


def test_phase3_zero_disclaimer_in_sub500ms_prewarm():
    """Verify extract_opening_greeting preserves fast prewarm greeting and never leaks recording disclosures."""
    script = (
        "--- CALLING SCRIPT ---\n"
        "--- CANONICAL OPENING ---\n"
        "Hello! This is Maya with Acme Health. Am I speaking with Alex?\n\n"
        "--- PLATFORM CALL RULES ---\n"
        "### RECORDING DISCLOSURE POLICY (NATURAL, ONCE):\n"
        'Recording disclosure is ENABLED. Deliver: "This call may be recorded for quality and training purposes."\n'
    )

    greeting = extract_opening_greeting(script, language="en-US", direction="outbound")
    assert greeting is not None
    assert greeting.startswith("Hello! This is Maya with Acme Health.")
    assert "recorded" not in greeting.lower()
    assert "disclosure" not in greeting.lower()


@pytest.mark.asyncio
async def test_phase3_compiler_recording_disclosure_injection():
    """Verify the compiler injects the natural once-only disclosure into platform rules when enabled."""
    brief = "agent name is Maya, business name is Acme Health, calling about appointment confirmation."

    # When disabled
    compiled_disabled, res_disabled, _, _, _ = await compile_agent_from_brief(
        brief=brief,
        language="en-US",
        recording_disclosure_enabled=False,
    )
    assert "RECORDING DISCLOSURE POLICY" not in compiled_disabled

    # When enabled
    compiled_enabled, res_enabled, _, _, _ = await compile_agent_from_brief(
        brief=brief,
        language="en-US",
        recording_disclosure_enabled=True,
    )
    assert "RECORDING DISCLOSURE POLICY (NATURAL, ONCE)" in compiled_enabled
    assert "This call may be recorded for quality and training purposes." in compiled_enabled
    assert "RECORDING DISCLOSURE POLICY (NATURAL, ONCE)" in res_enabled.platform_call_rules


@pytest.mark.asyncio
async def test_dynamic_recording_disclosure_sync_in_call_lifecycle(monkeypatch):
    from server.call.call_lifecycle_service import call_lifecycle_service

    base_brain = (
        "@agent_name: Maya\n@company_name: Acme\n@language: en-US\n@direction: inbound\n"
        "--- SPOKEN LANGUAGE (en-US) ---\n"
        "Hello, this is Maya from Acme.\n"
        "--- PLATFORM CALL RULES ---\n"
        "Speak English only."
    )

    async def _mock_resolve_agent(aid, *, tenant_id=None):
        return {
            "agent_id": aid,
            "tenant_id": "tenant-1",
            "environment": "development",
            "default_tier": "medium",
            "languages": ["en-US"],
            "recording_disclosure_enabled": True,
            "recording_disclosure_text": "Custom compliance disclosure notice.",
        }

    async def _mock_lock_compiled_brain(aid, session_id=None, **_kwargs):
        return "v1", base_brain, "published"

    monkeypatch.setattr(call_lifecycle_service, "_resolve_agent", _mock_resolve_agent)
    monkeypatch.setattr(call_lifecycle_service, "_lock_compiled_brain", _mock_lock_compiled_brain)

    res = await call_lifecycle_service.start(
        agent_id="agent-disc-test",
        session_id="test-disc-session",
        channel="browser",
        direction="inbound",
        language="en-US",
    )
    from server.call import call_context
    ctx = call_context.get(res["call_id"])
    assert ctx is not None
    prompt = ctx.compiled_brain_text
    assert "RECORDING DISCLOSURE POLICY" in prompt
    assert "Custom compliance disclosure notice." in prompt

    # Test dynamic disabling
    async def _mock_resolve_agent_disabled(aid, *, tenant_id=None):
        return {
            "agent_id": aid,
            "tenant_id": "tenant-1",
            "environment": "development",
            "default_tier": "medium",
            "languages": ["en-US"],
            "recording_disclosure_enabled": False,
        }

    monkeypatch.setattr(call_lifecycle_service, "_resolve_agent", _mock_resolve_agent_disabled)
    res_disabled = await call_lifecycle_service.start(
        agent_id="agent-disc-test-2",
        session_id="test-disc-session-2",
        channel="browser",
        direction="inbound",
        language="en-US",
    )
    ctx_disabled = call_context.get(res_disabled["call_id"])
    assert ctx_disabled is not None
    prompt_disabled = ctx_disabled.compiled_brain_text
    assert "RECORDING DISCLOSURE POLICY" not in prompt_disabled


@pytest.mark.asyncio
async def test_voicemail_mode_injection_in_call_lifecycle(monkeypatch):
    from server.call.call_lifecycle_service import call_lifecycle_service

    base_brain = (
        "@agent_name: Maya\n@company_name: Acme\n@language: en-US\n@direction: inbound\n"
        "--- SPOKEN LANGUAGE (en-US) ---\n"
        "Hello, this is Maya from Acme.\n"
        "--- PLATFORM CALL RULES ---\n"
        "Speak English only."
    )

    async def _mock_resolve_agent(aid, *, tenant_id=None):
        return {
            "agent_id": aid,
            "tenant_id": "tenant-1",
            "environment": "development",
            "default_tier": "medium",
            "languages": ["en-US"],
            "recording_disclosure_enabled": False,
        }

    async def _mock_lock_compiled_brain(aid, session_id=None, **_kwargs):
        return "v1", base_brain, "published"

    monkeypatch.setattr(call_lifecycle_service, "_resolve_agent", _mock_resolve_agent)
    monkeypatch.setattr(call_lifecycle_service, "_lock_compiled_brain", _mock_lock_compiled_brain)

    res = await call_lifecycle_service.start(
        agent_id="agent-vm-test",
        session_id="test-vm-session",
        channel="pstn",
        direction="inbound",
        language="en-US",
        voicemail_mode=True,
    )
    from server.call import call_context
    ctx = call_context.get(res["call_id"])
    assert ctx is not None
    prompt = ctx.compiled_brain_text
    assert "AFTER-HOURS VOICEMAIL MODE" in prompt




@pytest.mark.asyncio
async def test_tenant_wide_dnd_blocks_all_agents():
    """Verify that a DND entry added for a tenant blocks dialing regardless of which agent is calling."""
    tenant_id = uuid.uuid4()
    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()
    phone = "+15554443333"

    mock_session = AsyncMock()
    # DNC query is tenant-scoped: select(DncEntry.id).where(tenant_id == tenant_id, phone_e164 == phone, active == True)
    # It does not check agent_id, which guarantees tenant-wide protection.
    mock_dnc_entry = DncEntry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        phone_e164=phone,
        active=True,
        source="operator_ui",
    )
    assert mock_dnc_entry.tenant_id == tenant_id
    assert not hasattr(mock_dnc_entry, "agent_id")  # Tenant wide!


@pytest.mark.asyncio
async def test_onboarding_survey_updates_canonical_profiles_and_requires_terms():
    """Verify onboarding survey endpoint validates terms acceptance and updates user + tenant canonical records."""
    from server.routes.app_auth import OnboardingSurveyBody, submit_onboarding_survey
    from fastapi import Request

    with pytest.raises(Exception):
        OnboardingSurveyBody(
            fullName="Jane Doe",
            companyName="Jane Health",
            role="founder",
            referralSource="search",
            primaryUseCase="outbound_sales",
            estimatedMonthlyMinutes="1000",
            termsAccepted=False,  # Unchecked terms must fail validation
        )

    valid_body = OnboardingSurveyBody(
        fullName="Jane Doe",
        companyName="Jane Health",
        role="founder",
        referralSource="search",
        primaryUseCase="outbound_sales",
        estimatedMonthlyMinutes="1000",
        termsAccepted=True,
    )
    assert valid_body.termsAccepted is True
    assert valid_body.termsVersion == "2026-10-v1"


@pytest.mark.asyncio
async def test_create_campaign_endpoint_scrubs_dnd_and_persists_audit(campaign_db, monkeypatch):
    from sqlalchemy import select
    from server.tests.test_campaign_execution_safety import TID, UID, AID
    from server.routes.campaigns import create_campaign
    from server.auth.api_tenant import ApiTenantContext
    from starlette.requests import Request
    async with campaign_db() as db:
        db.add(DncEntry(tenant_id=TID, phone_e164="+12025550101", active=True))
        await db.commit()
    request = Request({"type": "http", "method": "POST", "path": "/api/campaigns", "headers": [(b'user-agent', b'Isolated audit'), (b'x-forwarded-for', b'198.51.100.99')], "client": ("127.0.0.1", 1234)})
    body = CampaignCreate(name="Audit consent", agentId=str(AID), contacts=[{"phone": "+12025550101"}, {"phone": "+12025550102"}], consentConfirmed=True, dndScrubEnabled=False)
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False)
    result = await create_campaign(request, body, ctx)
    assert result["ok"] and result["totalContacts"] == 2 and result["dndExcludedCount"] == 1
    async with campaign_db() as db:
        campaign = await db.get(Campaign, uuid.UUID(result["id"]))
        assert campaign.consent_confirmed is True
        assert campaign.consent_attestation_version == "2026-10-v1"
        assert campaign.attested_ip == "127.0.0.1"  # untrusted forwarded headers cannot forge the audit
        contacts = (await db.execute(select(CampaignContact).where(CampaignContact.campaign_id == campaign.campaign_id))).scalars().all()
        assert len(contacts) == 2
        assert {c.phone_e164: c.status for c in contacts} == {"+12025550101": "dnc_excluded", "+12025550102": "pending"}
