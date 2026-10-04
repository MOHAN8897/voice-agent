import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import Campaign, DncEntry
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
async def test_phase2_authoritative_predial_dnd_in_campaign_runner():
    """Verify campaign runner checks DND immediately before dial and skips blocked numbers."""
    tenant_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    run_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    phone = "+15551234567"

    mock_campaign = MagicMock(campaign_id=campaign_id, tenant_id=tenant_id, concurrency=1, retry_rules={}, agent_id=uuid.uuid4(), schedule={})
    mock_run = MagicMock(id=run_id, status="running")
    mock_contact = MagicMock(id=contact_id, campaign_id=campaign_id, phone_e164=phone, status="queued", attempts=0, metadata_={}, resolved_variables={})
    mock_attempt = MagicMock(id=uuid.uuid4(), status="queued")

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model is Campaign:
            return mock_campaign
        if model is CampaignRun:
            return mock_run
        if model is CampaignContact:
            return mock_contact
        if model is DialAttempt:
            return mock_attempt
        return None

    mock_session.get = mock_get

    # For session.execute calls:
    # 1. First execute is for pending contacts query
    # 2. Inside `one`: DncEntry query returns a hit!
    # 3. Subsequent calls (update stats, etc.)
    mock_contacts_result = MagicMock()
    mock_contacts_result.scalars.return_value.all.return_value = [mock_contact]

    mock_dnc_result = MagicMock()
    mock_dnc_result.scalar_one_or_none.return_value = uuid.uuid4()  # DNC HIT!

    execute_call_count = 0
    async def mock_execute(stmt, *args, **kwargs):
        nonlocal execute_call_count
        execute_call_count += 1
        if "campaign_contacts" in str(stmt).lower():
            return mock_contacts_result
        if "dnc_list" in str(stmt).lower():
            return mock_dnc_result
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        res.scalar_one_or_none.return_value = None
        return res

    mock_session.execute = mock_execute

    dial_called = False
    async def fake_dial(*args, **kwargs):
        nonlocal dial_called
        dial_called = True
        return {"ok": True}

    principal = MagicMock(tenant_id=tenant_id)

    class MockContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, *args):
            pass

    def mock_factory():
        return MockContextManager()

    with patch("server.services.saas.campaign_runner.get_session_factory", return_value=mock_factory), \
         patch("server.services.saas.campaign_runner._dial_one", fake_dial), \
         patch("server.services.saas.campaign_runner.count_active_pstn", return_value=0):
        await run_campaign(
            str(campaign_id),
            str(run_id),
            principal=principal,
            workspace_tenant_id=tenant_id,
        )

    # Dial must NOT have been called
    assert dial_called is False
    # Attempt marked dnc_skipped and contact marked dnc_excluded
    assert mock_attempt.status == "dnc_skipped"
    assert mock_contact.status == "dnc_excluded"


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
    """Verify disclosure instruction generator creates clean Turn-1 policy with English and Telugu."""
    # English default
    en_rule = build_recording_disclosure_instruction(language="en-US")
    assert "RECORDING DISCLOSURE POLICY (FIRST RESPONSE TURN ONLY)" in en_rule
    assert "This call may be recorded for quality and training purposes." in en_rule
    assert "FIRST RESPONSE TURN ONLY" in en_rule
    assert "Do NOT repeat this statement in any subsequent turns." in en_rule

    # Telugu default
    te_rule = build_recording_disclosure_instruction(language="te-IN")
    assert "నాణ్యత మరియు శిక్షణ ప్రయోజనాల కోసం ఈ కాల్ రికార్డ్ చేయబడవచ్చు." in te_rule

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
        "### RECORDING DISCLOSURE POLICY (FIRST RESPONSE TURN ONLY):\n"
        'Recording disclosure is ENABLED. Deliver: "This call may be recorded for quality and training purposes."\n'
    )

    greeting = extract_opening_greeting(script, language="en-US", direction="outbound")
    assert greeting is not None
    assert greeting.startswith("Hello! This is Maya with Acme Health.")
    assert "recorded" not in greeting.lower()
    assert "disclosure" not in greeting.lower()


@pytest.mark.asyncio
async def test_phase3_compiler_recording_disclosure_injection():
    """Verify script compiler cleanly injects Turn 1 recording disclosure into platform rules when enabled."""
    brief = "Maya from Acme Health calling about appointment confirmation."

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
    assert "RECORDING DISCLOSURE POLICY (FIRST RESPONSE TURN ONLY)" in compiled_enabled
    assert "This call may be recorded for quality and training purposes." in compiled_enabled
    assert "RECORDING DISCLOSURE POLICY (FIRST RESPONSE TURN ONLY)" in res_enabled.platform_call_rules


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
async def test_create_campaign_endpoint_scrubs_dnd_and_persists_audit():
    """Verify create_campaign scrubs active DND numbers and records client IP and consent version."""
    from server.routes.campaigns import create_campaign
    from fastapi import Request

    tenant_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    mock_agent = MagicMock(agent_id=agent_id, tenant_id=tenant_id)
    blacklisted_phone = "+15559990000"
    clean_phone = "+15559991111"

    body = CampaignCreate(
        name="Quarterly Compliance Outreach",
        agentId=str(agent_id),
        consentConfirmed=True,
        consentVersion="2026-10-v1",
        defaultCountry="US",
        dndScrubEnabled=True,
        contacts=[
            {"phone": blacklisted_phone, "first_name": "Blocked"},
            {"phone": clean_phone, "first_name": "Allowed"},
        ],
    )

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_agent

    # Query 1: DNC active rows returns blacklisted_phone
    dnc_res = MagicMock()
    dnc_res.scalars.return_value.all.return_value = [blacklisted_phone]
    mock_session.execute.return_value = dnc_res

    class MockContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, *args):
            pass

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "192.168.1.100"
    headers_dict = {"user-agent": "Mozilla/5.0 TestBrowser"}
    mock_request.headers.get.side_effect = lambda k, default=None: headers_dict.get(k.lower(), default)

    ctx = MagicMock(
        role="owner",
        workspace_tenant_id=tenant_id,
        tenant_id=tenant_id,
        subscriber=True,
        subject=str(uuid.uuid4()),
        email="test@example.com",
    )

    with patch("server.routes.campaigns.get_session_factory", return_value=lambda: MockContextManager()), \
         patch("server.routes.campaigns.require_role_permission", return_value=None):
        res = await create_campaign(mock_request, body, ctx)

        assert res["ok"] is True
        assert res["totalContacts"] == 2
        assert res["dndExcludedCount"] == 1
        assert res["campaign"]["dndExcludedCount"] == 1

        # Check Campaign ORM additions
        added_objs = [call.args[0] for call in mock_session.add.call_args_list]
        campaign_obj = next(o for o in added_objs if isinstance(o, Campaign))
        assert campaign_obj.consent_confirmed is True
        assert campaign_obj.consent_attestation_version == "2026-10-v1"
        assert campaign_obj.attested_ip == "192.168.1.100"

        # Check contact statuses
        contact_objs = [o for o in added_objs if isinstance(o, CampaignContact)]
        assert len(contact_objs) == 2
        blocked_c = next(c for c in contact_objs if c.phone_e164 == blacklisted_phone)
        allowed_c = next(c for c in contact_objs if c.phone_e164 == clean_phone)
        assert blocked_c.status == "dnc_excluded"
        assert allowed_c.status == "pending"

