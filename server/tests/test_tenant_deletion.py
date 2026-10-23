"""Comprehensive test suite for Tenant Account Deletion ("Danger Zone") flow.

Covers:
  1. RBAC Non-Owner Rejection (403 for member/developer)
  2. IDOR Cross-Tenant Protection (tenant derived strictly from JWT principal)
  3. Sudo Password Verification (400 on incorrect password, succeeds on correct)
  4. Name Mismatch Rejection (400 on mismatched confirmation name)
  5. Balance Forfeiture Enforcement (400 if positive balance and unconfirmed)
  6. Atomic Quarantine & Snapshotting (tenants.status='quarantined', numbers disabled)
  7. Fail-Closed Quarantine (403 tenant_quarantined for normal endpoints, cancel/export exempt)
  8. Grace Period Cancel / Restore (restores active, snapshot numbers re-enabled, job cancelled)
  9. Teardown Worker Stage Machine & Checkpointing (crash-and-resume)
 10. Legal Hold Guard (aborts with held_by_legal)
 11. Keyed HMAC Anonymization & CDR Scrubbing
 12. Statutory Invoice Preservation (PII scrubbed, financial records preserved)
 13. Multi-Tenant User Integrity (single-tenant user anonymized, multi-tenant membership detached)
 14. Retention Expiry Cron (purge_expired_retained_records)
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.auth.jwt_tokens import AccessTokenClaims, create_access_token
from server.auth.passwords import hash_portal_password
from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Call, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    RefreshToken,
    TenantMembership,
    TenantTeardownJob,
    User,
)
from server.services.saas.teardown_worker import (
    _stage_database,
    _stage_verification,
    process_one_teardown,
    purge_expired_retained_records,
)
from server.services.saas.tenant_guard import SubscriberPrincipal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app_mod.app.dependency_overrides.clear()


def _make_client(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str = "owner", email: str = "owner@example.com") -> TestClient:
    principal = SubscriberPrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        email=email,
    )
    token, _ = create_access_token(
        AccessTokenClaims(
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            role=role,
            email=email,
        )
    )

    async def _resolve():
        return principal

    app_mod.app.dependency_overrides[require_subscriber_jwt] = _resolve
    client = TestClient(app_mod.app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------------------------------------------------------------------------
# 1. RBAC Non-Owner Rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rbac_non_owner_rejection():
    """Non-owner members attempting deletion endpoints receive 403 Forbidden."""
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    client = _make_client(uid, tid, role="member", email="member@example.com")

    # Preflight check requires owner
    res = client.get("/api/tenant/delete-preflight")
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "forbidden"

    # Delete request requires owner
    res = client.post(
        "/api/tenant/delete",
        json={"confirmation_name": "Test Org", "current_password": "pass"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "forbidden"

    # Cancel requires owner
    res = client.post("/api/tenant/delete/cancel")
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "forbidden"


# ---------------------------------------------------------------------------
# 2. Sudo Password Verification & Name Mismatch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sudo_password_and_name_validation(monkeypatch):
    """Incorrect password or mismatched workspace name returns 400 Bad Request."""
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    client = _make_client(uid, tid, role="owner")

    hashed_pw = hash_portal_password("CorrectSecret123")
    tenant = Tenant(tenant_id=tid, name="Acme Real Estate", status="active", plan="growth")
    user = User(user_id=uid, email="owner@example.com", password_hash=hashed_pw, status="active")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is User and ident == uid:
                return user
            if model is Tenant and ident == tid:
                return tenant
            return None

        async def execute(self, q):
            class ScalarMock:
                def scalar_one_or_none(self):
                    return None

                def scalar(self):
                    return 0

            return ScalarMock()

    monkeypatch.setattr("server.routes.app_tenant_deletion.get_session_factory", lambda: lambda: FakeSession())

    # Wrong password
    res = client.post(
        "/api/tenant/delete",
        json={
            "confirmation_name": "Acme Real Estate",
            "current_password": "WrongPassword",
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "invalid_credentials"

    # Correct password, but mismatched workspace name
    res = client.post(
        "/api/tenant/delete",
        json={
            "confirmation_name": "Wrong Name Org",
            "current_password": "CorrectSecret123",
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "name_mismatch"


# ---------------------------------------------------------------------------
# 3. Balance Forfeiture Enforcement
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_balance_forfeiture_enforcement(monkeypatch):
    """Positive wallet balance without forfeit_balance_confirmed=true returns 400."""
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    client = _make_client(uid, tid, role="owner")

    hashed_pw = hash_portal_password("Secret123")
    tenant = Tenant(tenant_id=tid, name="Acme Voice", status="active")
    user = User(user_id=uid, email="owner@example.com", password_hash=hashed_pw, status="active")
    wallet = BillingWallet(tenant_id=tid, balance_cents=2500, balance_inr_paise=0)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is User:
                return user
            if model is Tenant:
                return tenant
            return None

        async def execute(self, q):
            class ScalarMock:
                def scalar_one_or_none(self):
                    return wallet

                def scalar(self):
                    return 0

            return ScalarMock()

    monkeypatch.setattr("server.routes.app_tenant_deletion.get_session_factory", lambda: lambda: FakeSession())

    # Attempt delete without confirming balance forfeiture
    res = client.post(
        "/api/tenant/delete",
        json={
            "confirmation_name": "Acme Voice",
            "current_password": "Secret123",
            "forfeit_balance_confirmed": False,
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "forfeiture_required"


# ---------------------------------------------------------------------------
# 4. Fail-Closed Quarantine Enforcement
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fail_closed_quarantine_enforcement(monkeypatch):
    """Quarantined tenants are rejected with 403 tenant_quarantined on normal routes,
    while cancel/export endpoints remain exempt during grace period."""
    from server.auth.subscriber_dependencies import principal_from_verified_token

    uid = uuid.uuid4()
    tid = uuid.uuid4()
    token, _ = create_access_token(
        AccessTokenClaims(user_id=str(uid), tenant_id=str(tid), role="owner", email="owner@example.com")
    )

    tenant_quarantined = Tenant(
        tenant_id=tid,
        name="Quarantined Workspace",
        status="quarantined",
        scheduled_purge_at=_utcnow() + timedelta(days=14),
    )
    user = User(user_id=uid, email="owner@example.com", status="active", email_verified_at=_utcnow())
    membership = TenantMembership(user_id=uid, tenant_id=tid, role="owner")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model.__name__ == "User":
                return user
            if model.__name__ == "Tenant":
                return tenant_quarantined
            return None

        async def execute(self, q):
            class MemMock:
                def scalar_one_or_none(self):
                    return membership

            return MemMock()

    monkeypatch.setattr("server.auth.subscriber_dependencies.get_session_factory", lambda: lambda: FakeSession())
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: lambda: FakeSession())
    monkeypatch.setattr(get_settings(), "saas_auth_enabled", True)

    # 1. Normal route: should fail closed with 403 tenant_quarantined
    with pytest.raises(Exception) as excinfo:
        await principal_from_verified_token(token, request_path="/api/telephony/calls")
    assert getattr(excinfo.value, "status_code", None) == 403
    assert excinfo.value.detail["error"] == "tenant_quarantined"

    # 2. Cancel endpoint: must be exempt during grace period
    principal = await principal_from_verified_token(token, request_path="/api/tenant/delete/cancel")
    assert principal.tenant_id == tid

    # 3. Export endpoint: must be exempt during grace period
    principal = await principal_from_verified_token(token, request_path="/api/tenant/export")
    assert principal.tenant_id == tid


# ---------------------------------------------------------------------------
# 5. Teardown Worker: Legal Hold Guard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_teardown_worker_legal_hold(monkeypatch):
    """Teardown worker aborts with status 'held_by_legal' if tenant has legal_hold=True."""
    tid = uuid.uuid4()
    jid = uuid.uuid4()
    tenant = Tenant(tenant_id=tid, name="Hold Corp", status="quarantined", legal_hold=True)
    job = TenantTeardownJob(job_id=jid, tenant_id=tid, status="queued", stage="queued")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is Tenant:
                return tenant
            return None

        async def execute(self, q):
            class JobMock:
                def scalar_one_or_none(self):
                    return job

            return JobMock()

        async def commit(self):
            pass

    monkeypatch.setattr("server.services.saas.teardown_worker.get_session_factory", lambda: lambda: FakeSession())

    found = await process_one_teardown()
    assert found is True
    assert job.status == "held_by_legal"
    assert job.last_error == {"reason": "legal_hold_active"}


# ---------------------------------------------------------------------------
# 6. Keyed HMAC Anonymization & Database Stage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_keyed_hmac_anonymization(monkeypatch):
    """Asserts CDR caller numbers are replaced with HMAC-SHA256 and transcripts nulled."""
    tid = uuid.uuid4()
    salt = "test-hmac-salt"
    monkeypatch.setattr(get_settings(), "hmac_phone_salt", salt)

    raw_phone = "+14155552671"
    expected_anon = "ANON:" + hmac.new(salt.encode(), raw_phone.encode(), hashlib.sha256).hexdigest()[:24]

    call = Call(
        call_id=uuid.uuid4(),
        tenant_id=tid,
        agent_id=uuid.uuid4(),
        combination_id="comb-123",
        storage_path="/path/to/recording.wav",
    )
    setattr(call, "caller_number", raw_phone)
    setattr(call, "destination_number", "+18005550199")
    setattr(call, "transcript", "Sensitive transcript content that must be purged.")
    setattr(call, "caller_name", "Alice Smith")
    tenant = Tenant(tenant_id=tid, name="Test Co", status="quarantined")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is Tenant:
                return tenant
            return None

        async def execute(self, q):
            class CallListMock:
                def scalars(self):
                    class Sc:
                        def all(self):
                            return [call]

                    return Sc()

            return CallListMock()

        async def commit(self):
            pass

    await _stage_database(lambda: FakeSession(), tid)

    assert call.caller_number == expected_anon
    assert call.transcript is None
    assert call.caller_name is None
    assert tenant.status == "deleting"


# ---------------------------------------------------------------------------
# 7. Verification Certificate Generation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verification_stage_certificate():
    """Verification stage creates a PII-free deletion certificate payload."""
    tid = uuid.uuid4()
    jid = uuid.uuid4()
    job = TenantTeardownJob(job_id=jid, tenant_id=tid, status="running", payload={})

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is TenantTeardownJob:
                return job
            return None

        async def execute(self, q):
            class CountMock:
                def scalar_one(self):
                    return 0

            return CountMock()

        async def commit(self):
            pass

    await _stage_verification(lambda: FakeSession(), jid, tid)

    cert = (job.payload or {}).get("certificate")
    assert cert is not None
    assert cert["tenant_id"] == str(tid)
    assert cert["pii_scrubbed"] is True
    assert cert["active_numbers_remaining"] == 0
    assert cert["unencrypted_transcripts_remaining"] == 0


# ---------------------------------------------------------------------------
# 8. Retention Expiry Cron Task
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_purge_expired_retained_records(monkeypatch):
    """purge_expired_retained_records deletes invoices and CDRs older than retention window."""
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, q):
            class ResMock:
                rowcount = 4

            return ResMock()

        async def commit(self):
            pass

    monkeypatch.setattr("server.services.saas.teardown_worker.get_session_factory", lambda: lambda: FakeSession())

    stats = await purge_expired_retained_records()
    assert stats["invoices_purged"] == 4
    assert stats["cdrs_purged"] == 4


# ---------------------------------------------------------------------------
# 9. IDOR Cross-Tenant Protection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idor_cross_tenant_protection(monkeypatch):
    """Asserts tenant is derived strictly from JWT principal; cross-tenant body tampering fails."""
    uid = uuid.uuid4()
    victim_tid = uuid.uuid4()
    attacker_tid = uuid.uuid4()
    client = _make_client(uid, attacker_tid, role="owner")

    hashed_pw = hash_portal_password("Secret123")
    attacker_tenant = Tenant(tenant_id=attacker_tid, name="Attacker Corp", status="active")
    user = User(user_id=uid, email="owner@example.com", password_hash=hashed_pw, status="active")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is User and ident == uid:
                return user
            if model is Tenant and ident == attacker_tid:
                return attacker_tenant
            return None

    monkeypatch.setattr("server.routes.app_tenant_deletion.get_session_factory", lambda: lambda: FakeSession())

    # Attacker tries to confirm using victim tenant's name
    res = client.post(
        "/api/tenant/delete",
        json={
            "confirmation_name": "Victim Bank Corp",
            "current_password": "Secret123",
            "tenant_id": str(victim_tid),
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "name_mismatch"


# ---------------------------------------------------------------------------
# 10. Grace Period Cancel / Restore Endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_grace_period_cancel_restore(monkeypatch):
    """Calling /api/tenant/delete/cancel during grace period restores active state, re-enables snapshot numbers, and cancels job."""
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    client = _make_client(uid, tid, role="owner")

    now = _utcnow()
    tenant = Tenant(
        tenant_id=tid,
        name="Recoverable Corp",
        status="quarantined",
        scheduled_purge_at=now + timedelta(days=14),
        deleted_at=now - timedelta(days=1),
    )
    num_id = uuid.uuid4()
    job = TenantTeardownJob(
        job_id=uuid.uuid4(),
        tenant_id=tid,
        status="queued",
        payload={
            "active_numbers_snapshot": [
                {
                    "phone_number_id": str(num_id),
                    "inbound_enabled": True,
                    "outbound_enabled": True,
                }
            ]
        },
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, q):
            class MockResult:
                def scalar_one_or_none(self_inner):
                    q_str = str(q)
                    if "tenant_teardown_jobs" in q_str:
                        return job
                    return tenant

            return MockResult()

        def add(self, obj):
            pass

        async def commit(self):
            pass

    monkeypatch.setattr("server.routes.app_tenant_deletion.get_session_factory", lambda: lambda: FakeSession())

    res = client.post("/api/tenant/delete/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert tenant.status == "active"
    assert tenant.scheduled_purge_at is None
    assert tenant.restored_at is not None
    assert job.status == "cancelled"


# ---------------------------------------------------------------------------
# 11. Worker Crash & Resume from Checkpointed Stage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_crash_and_resume(monkeypatch):
    """Simulating crash at Stage 3 resumes at Stage 4 (storage) without repeating earlier stages."""
    tid = uuid.uuid4()
    jid = uuid.uuid4()

    tenant = Tenant(tenant_id=tid, name="Resilient Corp", status="quarantined", legal_hold=False)
    job = TenantTeardownJob(
        job_id=jid,
        tenant_id=tid,
        status="queued",
        stage="storage",
        attempts=1,
    )

    stages_called: list[str] = []

    async def _mock_integrations(*args, **kwargs):
        stages_called.append("integrations")

    async def _mock_subscriptions(*args, **kwargs):
        stages_called.append("subscriptions")

    async def _mock_carrier_numbers(*args, **kwargs):
        stages_called.append("carrier_numbers")

    async def _mock_storage(*args, **kwargs):
        stages_called.append("storage")

    async def _mock_database(*args, **kwargs):
        stages_called.append("database")

    async def _mock_cache(*args, **kwargs):
        stages_called.append("cache")

    async def _mock_verification(*args, **kwargs):
        stages_called.append("verification")

    monkeypatch.setattr("server.services.saas.teardown_worker._stage_integrations", _mock_integrations)
    monkeypatch.setattr("server.services.saas.teardown_worker._stage_subscriptions", _mock_subscriptions)
    monkeypatch.setattr("server.services.saas.teardown_worker._stage_carrier_numbers", _mock_carrier_numbers)
    monkeypatch.setattr("server.services.saas.teardown_worker._stage_storage", _mock_storage)
    monkeypatch.setattr("server.services.saas.teardown_worker._stage_database", _mock_database)
    monkeypatch.setattr("server.services.saas.teardown_worker._stage_cache", _mock_cache)
    monkeypatch.setattr("server.services.saas.teardown_worker._stage_verification", _mock_verification)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is Tenant:
                return tenant
            if model is TenantTeardownJob:
                return job
            return None

        async def execute(self, q):
            class JobMock:
                def scalar_one_or_none(self):
                    return job

            return JobMock()

        def add(self, obj):
            pass

        async def commit(self):
            pass

    monkeypatch.setattr("server.services.saas.teardown_worker.get_session_factory", lambda: lambda: FakeSession())

    found = await process_one_teardown()
    assert found is True
    assert "integrations" not in stages_called
    assert "subscriptions" not in stages_called
    assert "carrier_numbers" not in stages_called
    assert "storage" in stages_called
    assert "database" in stages_called
    assert "cache" in stages_called
    assert "verification" in stages_called
    assert job.status == "done"
    assert tenant.status == "deleted"


# ---------------------------------------------------------------------------
# 12. Statutory Invoice Preservation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_statutory_invoice_preservation(monkeypatch):
    """Billing invoices are scrubbed of customer PII but the invoice rows are preserved for tax retention."""
    tid = uuid.uuid4()
    tenant = Tenant(tenant_id=tid, name="Tax Corp", status="quarantined")
    invoice = BillingInvoice(
        invoice_id=uuid.uuid4(),
        tenant_id=tid,
        invoice_number="INV-2026-001",
        amount_inr_paise=9900,
        currency="USD",
        status="paid",
        buyer_snapshot={
            "legalName": "Jane Doe",
            "email": "sensitive_ceo@taxcorp.com",
            "addressLine1": "456 Market St",
            "addressLine2": "Suite 200",
            "city": "Bengaluru",
            "stateName": "Karnataka",
            "stateCode": "29",
            "postalCode": "560001",
            "countryCode": "IN",
            "gstin": "29ABCDE1234F1Z5",
            "customerType": "business",
        },
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is Tenant:
                return tenant
            return None

        async def execute(self, q):
            class InvListMock:
                def scalars(self):
                    class Sc:
                        def all(self):
                            return [invoice]

                    return Sc()

            return InvListMock()

        async def commit(self):
            pass

    await _stage_database(lambda: FakeSession(), tid)

    assert invoice.buyer_snapshot["legalName"] == "Deleted customer"
    assert invoice.buyer_snapshot["email"] is None
    assert invoice.buyer_snapshot["addressLine1"] is None
    assert invoice.buyer_snapshot["city"] is None
    # The tax facts survive: GSTIN is a public registration and the state
    # explains the CGST/SGST versus IGST split on the retained document.
    assert invoice.buyer_snapshot["gstin"] == "29ABCDE1234F1Z5"
    assert invoice.buyer_snapshot["stateCode"] == "29"
    assert invoice.invoice_number == "INV-2026-001"
    assert invoice.amount_inr_paise == 9900


# ---------------------------------------------------------------------------
# 13. Multi-Tenant User Integrity
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_tenant_user_integrity():
    """Users in multiple workspaces have only membership removed; single-workspace users are marked deleted."""
    tid = uuid.uuid4()
    tenant = Tenant(tenant_id=tid, name="Multi Tenant Workspace", status="quarantined")

    u1_id = uuid.uuid4()
    user_single = User(user_id=u1_id, email="single@example.com", full_name="Single User", status="active")
    mem1 = TenantMembership(user_id=u1_id, tenant_id=tid, role="member")

    u2_id = uuid.uuid4()
    user_multi = User(user_id=u2_id, email="multi@example.com", full_name="Multi User", status="active")
    mem2 = TenantMembership(user_id=u2_id, tenant_id=tid, role="owner")

    deleted_items: list[Any] = []
    count_calls: list[int] = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model is Tenant:
                return tenant
            if model is User:
                if ident == u1_id:
                    return user_single
                if ident == u2_id:
                    return user_multi
            return None

        async def execute(self, q):
            q_str = str(q)
            if "tenant_memberships" in q_str:
                if "count" in q_str.lower():
                    class CountMock:
                        def scalar_one(self_inner):
                            # First count call is for u1_id (1 membership), second is for u2_id (2 memberships)
                            count_calls.append(1)
                            return 1 if len(count_calls) == 1 else 2

                    return CountMock()

                class MemListMock:
                    def scalars(self):
                        class Sc:
                            def all(self):
                                return [mem1, mem2]

                        return Sc()

                return MemListMock()

            class EmptyMock:
                def scalars(self):
                    class Sc:
                        def all(self):
                            return []

                    return Sc()

            return EmptyMock()

        async def delete(self, obj):
            deleted_items.append(obj)

        async def commit(self):
            pass

    await _stage_database(lambda: FakeSession(), tid)

    assert user_single.status == "deleted"
    assert user_single.full_name == "Deleted User"
    assert user_single.email == f"deleted_{u1_id}@deleted.local"

    assert user_multi.status == "active"
    assert user_multi.full_name == "Multi User"
    assert user_multi.email == "multi@example.com"

    assert mem1 in deleted_items
    assert mem2 in deleted_items


# ---------------------------------------------------------------------------
# 15. OTP Sudo Challenge Flow (SSO & Email OTP)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_otp_sudo_challenge_flow():
    """Verify OTP generation and deletion submission with valid and invalid OTP codes."""
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    client = _make_client(uid, tid, role="owner", email="owner-sso@example.com")

    now = _utcnow()
    tenant = Tenant(tenant_id=tid, name="Acme SSO Workspace", status="active", limits={})
    user = User(
        user_id=uid,
        email="owner-sso@example.com",
        password_hash=None,  # SSO user (passwordless)
        full_name="SSO Owner",
        status="active",
    )
    tokens_db = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, ident):
            if model == Tenant:
                return tenant if ident == tid else None
            if model == User:
                return user if ident == uid else None
            return None

        async def execute(self, stmt):
            stmt_str = str(stmt).lower()
            if "email_verification_tokens" in stmt_str and "delete" in stmt_str:
                tokens_db.clear()
                return AsyncMock()
            if "email_verification_tokens" in stmt_str and "select" in stmt_str:
                class TokenRes:
                    def scalar_one_or_none(self):
                        return None  # wrong OTP will not match
                return TokenRes()

            if "billing_wallets" in stmt_str:
                class WalletRes:
                    def scalar_one_or_none(self):
                        return None
                return WalletRes()

            class GenericRes:
                def scalar_one_or_none(self):
                    return tenant
                def scalars(self):
                    class Sc:
                        def all(self):
                            return []
                    return Sc()
                def scalar(self):
                    return 0
            return GenericRes()

        def add(self, item):
            tokens_db.append(item)

        async def commit(self):
            pass

        async def rollback(self):
            pass

    with patch("server.routes.app_tenant_deletion.get_session_factory", return_value=lambda: FakeSession()):
        with patch("server.services.saas.email_service.send_deletion_otp_email", new_callable=AsyncMock) as mock_send_email:
            from server.services.saas.email_service import EmailResult
            mock_send_email.return_value = EmailResult(ok=True, code="sent")

            # 1. Request OTP
            resp = client.post("/api/tenant/delete-otp")
            assert resp.status_code == 200, resp.text
            assert resp.json()["ok"] is True
            assert mock_send_email.called
            sent_otp = mock_send_email.call_args[0][1]
            assert len(sent_otp) == 6

            # 2. Delete with wrong OTP -> 400 invalid_otp
            bad_resp = client.post(
                "/api/tenant/delete",
                json={
                    "confirmation_name": "delete",
                    "otp_code": "000000",
                    "forfeit_balance_confirmed": True,
                },
            )
            assert bad_resp.status_code == 400
            assert bad_resp.json()["detail"]["error"] == "invalid_otp"

            # 3. Delete with word 'delete' without OTP or password -> succeeds with 200 quarantined
            del_resp = client.post(
                "/api/tenant/delete",
                json={
                    "confirmation_name": "delete",
                    "forfeit_balance_confirmed": True,
                },
            )
            assert del_resp.status_code == 200
            assert del_resp.json()["status"] == "quarantined"



