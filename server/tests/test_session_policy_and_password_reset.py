"""Session policy, password reset auto-login, and tenant-safe call payloads.

Covers the audit findings these changes were made for:

  * a reset token signs the user in instead of dumping them back on the sign-in form
  * changing a password keeps the current session alive while revoking the others
  * a refresh older than the idle bound is refused even though the token is still
    inside its 30-day lifetime, and so is one past the absolute ceiling
  * a call payload a tenant can read contains no wholesale cost or vendor detail
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.db.models.entities import Tenant
from server.db.models.saas_models import PasswordResetToken, RefreshToken, TenantMembership, User
from server.services.saas import auth_service
from server.services.saas.call_redaction import (
    is_internal_viewer,
    redact_call_detail_for_tenant,
)
from server.services.saas.email_service import EmailResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _FakeResult:
    def __init__(self, *, one=None, rows=None, scalar=None):
        self._one = one
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._one

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _AsyncCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc):
        return False


class _FakeSession:
    """Records statements well enough for refresh / change / reset_password."""

    def __init__(self, *, user=None, token_row=None, membership_tenant=None, reset_row=None):
        self.user = user
        self.token_row = token_row
        self.membership_tenant = membership_tenant
        self.reset_row = reset_row
        self.added: list = []
        self.commits = 0
        self.family_revocations: list[str] = []
        self.deleted: list = []
        self.scalar_result = None

    async def execute(self, stmt):
        text = str(stmt)
        if "UPDATE refresh_tokens" in text:
            self.family_revocations.append(text)
            return _FakeResult(scalar=0)
        if "FROM refresh_tokens" in text and "revoked_at IS NULL" not in text:
            return _FakeResult(one=self.token_row)
        if "FROM tenant_memberships" in text:
            return _FakeResult(rows=[(self._membership(), self.membership_tenant)])
        if "FROM password_reset_tokens" in text:
            return _FakeResult(one=self.reset_row)
        return _FakeResult()

    async def scalar(self, _stmt):
        return self.scalar_result

    async def get(self, _model, _pk):
        return self.user

    def _membership(self) -> TenantMembership:
        return TenantMembership(
            user_id=self.user.user_id,
            tenant_id=self.membership_tenant.tenant_id,
            role="customer_admin",
            created_at=_utcnow(),
        )

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def harness(monkeypatch):
    """Builds a signed-in account with a session factory the service can use."""

    def build(
        *,
        created_at=None,
        last_active_at=None,
        absolute_expires_at=None,
        password="correct-horse-battery",
    ):
        user = User(
            user_id=uuid.uuid4(),
            email="owner@example.com",
            status="active",
            email_verified_at=_utcnow(),
            password_hash=__import__(
                "server.auth.passwords", fromlist=["hash_portal_password"]
            ).hash_portal_password(password),
            full_name="Owner",
        )
        tenant = Tenant(tenant_id=uuid.uuid4(), name="Owner Workspace", status="active")
        token_row = None
        if created_at is not None:
            token_row = RefreshToken(
                id=uuid.uuid4(),
                user_id=user.user_id,
                token_hash=hashlib.sha256(b"tok").hexdigest(),
                family_id=uuid.uuid4(),
                expires_at=_utcnow() + timedelta(days=30),
                created_at=created_at,
                last_active_at=last_active_at or created_at,
                absolute_expires_at=absolute_expires_at or (_utcnow() + timedelta(days=29)),
            )
        session = _FakeSession(
            user=user,
            token_row=token_row,
            membership_tenant=tenant,
            reset_row=None,
        )

        async def _no_wallet(*_a, **_k):
            return None

        monkeypatch.setattr(
            auth_service, "get_session_factory", lambda: (lambda: _AsyncCtx(session))
        )
        monkeypatch.setattr(auth_service, "_seed_admin_wallet", _no_wallet)
        return session, user, tenant

    return build


# --------------------------------------------------------------------------- #
# Password reset / change
# --------------------------------------------------------------------------- #


async def test_reset_password_returns_a_session(harness):
    """A valid reset token proves mailbox ownership: sign the user straight in."""
    from server.auth.passwords import verify_portal_password

    session, user, tenant = harness()
    session.reset_row = PasswordResetToken(
        token_hash=auth_service._hash_token("raw-token"),
        user_id=user.user_id,
        expires_at=_utcnow() + timedelta(hours=1),
        created_at=_utcnow(),
    )

    payload = await auth_service.reset_password("raw-token", "brand-new-password")

    assert payload["accessToken"]
    assert payload["refreshToken"]
    assert payload["user"]["email"] == user.email
    assert payload["tenant"]["tenantId"] == str(tenant.tenant_id)
    assert verify_portal_password(user.password_hash, "brand-new-password")
    assert session.commits == 1
    # Every other session for the account is revoked in the same transaction.
    assert any("UPDATE refresh_tokens" in sql for sql in session.family_revocations)


async def test_reset_password_rejects_an_unknown_token(harness):
    session, _user, _tenant = harness()
    session.reset_row = None
    with pytest.raises(ValueError) as excinfo:
        await auth_service.reset_password("raw-token", "brand-new-password")
    assert str(excinfo.value) == "invalid_token"


async def test_change_password_returns_a_session(harness):
    """The person who changes their password must not be signed out of that tab."""
    from server.auth.passwords import verify_portal_password

    session, user, tenant = harness()

    payload = await auth_service.change_password(
        user.user_id, "correct-horse-battery", "another-good-password"
    )

    assert payload["accessToken"]
    assert payload["refreshToken"]
    assert payload["tenant"]["tenantId"] == str(tenant.tenant_id)
    assert verify_portal_password(user.password_hash, "another-good-password")
    assert any("UPDATE refresh_tokens" in sql for sql in session.family_revocations)


async def test_change_password_rejects_the_wrong_current_password(harness):
    _session, user, _tenant = harness()
    with pytest.raises(ValueError) as excinfo:
        await auth_service.change_password(user.user_id, "not-the-password", "another-good-password")
    assert str(excinfo.value) == "invalid_credentials"


async def test_change_password_enforces_a_minimum_length(harness):
    _session, user, _tenant = harness()
    with pytest.raises(ValueError) as excinfo:
        await auth_service.change_password(user.user_id, "correct-horse-battery", "short")
    assert str(excinfo.value) == "password_too_short"


# --------------------------------------------------------------------------- #
# Sliding-window session policy
# --------------------------------------------------------------------------- #


async def test_refresh_refuses_a_token_past_the_idle_bound(harness):
    """The old behaviour kept a 30-day token alive no matter how idle it was."""
    session, _user, _tenant = harness(
        created_at=_utcnow() - timedelta(hours=6),
        last_active_at=_utcnow() - timedelta(hours=6),
    )

    with pytest.raises(ValueError) as excinfo:
        await auth_service.refresh("tok")
    assert str(excinfo.value) == "session_idle"
    # The whole family is burned, not just the presented token.
    assert session.family_revocations


async def test_refresh_refuses_a_token_past_the_absolute_ceiling(harness):
    """A script holding a session open must still have to re-authenticate."""
    session, _user, _tenant = harness(
        created_at=_utcnow() - timedelta(hours=25),
        last_active_at=_utcnow(),
        absolute_expires_at=_utcnow() - timedelta(minutes=1),
    )

    with pytest.raises(ValueError) as excinfo:
        await auth_service.refresh("tok")
    assert str(excinfo.value) == "session_absolute_max"
    assert session.family_revocations


def test_session_policy_exposes_the_bounds_the_client_mirrors():
    policy = auth_service.session_policy()
    assert policy["idleTimeoutMinutes"] > 0
    assert policy["absoluteMaxHours"] > 0
    assert policy["accessTokenMinutes"] > 0


async def test_rotation_carries_the_original_absolute_deadline():
    """Each rotation must not restart the clock, or the ceiling is never reached."""
    original = _utcnow() + timedelta(hours=3)
    session = _FakeSession(user=None)
    session.scalar_result = original

    inherited = await auth_service._session_absolute_deadline(
        session, uuid.uuid4(), default=_utcnow() + timedelta(hours=24), inherit=None
    )
    assert inherited == original


async def test_first_sign_in_gets_a_fresh_absolute_deadline():
    session = _FakeSession(user=None)
    session.scalar_result = None  # no token in this family yet
    deadline = await auth_service._session_absolute_deadline(
        session, uuid.uuid4(), default=_utcnow() + timedelta(hours=24), inherit=None
    )
    assert deadline - _utcnow() <= timedelta(hours=24, seconds=5)


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #


def test_tenant_call_payload_has_no_wholesale_cost_or_vendor_detail():
    payload = {
        "call_id": "c1",
        "agent_id": "a1",
        "channel": "pstn_realtime",
        "duration_sec": 91,
        "cost_usd": 0.14,
        "cost_inr": 12.4,
        "cost_inr_per_min": 8.1,
        "telnyx_inr": 6.2,
        "model_cost_inr": 4.1,
        "combination_id": "combo-9",
        "compiled_brain_version": "17",
        "dial_request_id": "dial-3",
        "transcript_source": "telnyx+gemini",
        "resolved_stack": {"llm": {"provider": "gemini", "model": "gemini-3.8-live"}},
        "pstn_forensics": {"derived_ms": {"answer_to_first_audio_sent": 1240}},
        "finalization": {"status": "complete", "ledger": "posted", "audio": "archived"},
        "usage": {
            "turns": 6,
            "duration_sec": 91,
            "telnyx_inr_per_min": 4.1,
            "gemini_list_audio_inr_per_min": 90.0,
            "model_cost_inr_per_min": 2.7,
            "fx_rate_inr": 95.64,
            "transcription_billing": "post_call_gemini_transcribe",
            "llm_model": "gemini-3.8-live",
        },
        "post_call_transcript": {"status": "done", "model": "gemini-3.5-transcribe"},
    }

    safe = redact_call_detail_for_tenant(payload)

    blob = repr(safe).lower()
    for leak in (
        "telnyx",
        "gemini",
        "openai",
        "cost_inr",
        "fx_rate",
        "combination_id",
        "resolved_stack",
        "pstn_forensics",
        "dial_request",
        "ledger",
    ):
        assert leak not in blob, f"{leak!r} leaked into the tenant payload"

    # Customer-facing numbers survive: they are what an invoice is reconciled against.
    assert safe["cost_usd"] == 0.14
    assert safe["duration_sec"] == 91
    assert safe["usage"]["turns"] == 6
    assert safe["finalization"]["status"] == "complete"
    assert safe["internal_fields_hidden"] is True


def test_internal_viewer_roles_are_explicit():
    assert is_internal_viewer("platform_admin")
    assert is_internal_viewer("administrator")
    assert is_internal_viewer("developer")
    assert not is_internal_viewer("customer_admin")
    assert not is_internal_viewer("customer_viewer")
    assert not is_internal_viewer("voice_engineer")
    assert not is_internal_viewer(None)


# --------------------------------------------------------------------------- #
# Email delivery honesty
# --------------------------------------------------------------------------- #


def test_email_result_carries_the_provider_reason():
    result = EmailResult(
        ok=False,
        code="domain_not_verified",
        detail="The hustlelabs.in domain is not verified.",
        provider_status=403,
    )
    assert not result
    assert result.code == "domain_not_verified"
    assert result.provider_status == 403