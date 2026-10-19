"""Tenant-scoped Vobiz customer_use onboarding and KYC state.

Vobiz returns a child auth token once. This module encrypts it before persistence,
keeps provisioning idempotent across retries, and never exposes credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.saas_models import VobizSubaccount

logger = logging.getLogger(__name__)

BUSINESS_TYPES = frozenset(
    {
        "individual",
        "proprietorship",
        "private_limited",
        "llp",
        "partnership",
        "public_limited",
        "trust",
        "society",
        "huf",
        "government",
    }
)
_STATUS_CACHE_SECONDS = 30
_VERIFICATION_VALUES = frozenset({"not_started", "pending", "verified", "failed"})


class VoiceKycError(RuntimeError):
    def __init__(self, code: str, *, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fernet():
    from cryptography.fernet import Fernet

    key = str(get_settings().vobiz_subaccount_encryption_key or "").strip()
    if not key:
        raise VoiceKycError("voice_kyc_encryption_not_configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise VoiceKycError("voice_kyc_encryption_invalid") from exc


def encrypt_subaccount_token(tenant_id: UUID, token: str) -> str:
    if not token:
        raise VoiceKycError("voice_credentials_unavailable")
    payload = f"{tenant_id}\0{token}".encode()
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_subaccount_token(tenant_id: UUID, encrypted: str) -> str:
    from cryptography.fernet import InvalidToken

    try:
        raw = _fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError, ValueError) as exc:
        raise VoiceKycError("voice_credentials_unavailable") from exc
    prefix = f"{tenant_id}\0"
    if not raw.startswith(prefix) or not raw[len(prefix) :]:
        raise VoiceKycError("voice_credentials_tenant_mismatch")
    return raw[len(prefix) :]


def _safe_name(value: str) -> str:
    name = " ".join(str(value or "").split()).strip()
    if not 2 <= len(name) <= 255:
        raise VoiceKycError("legal_name_required", status_code=400)
    return name


def _trusted_return_url(candidate: str | None) -> str:
    settings = get_settings()
    configured = urlsplit(str(settings.voxly_frontend_url or "").strip())
    if configured.scheme not in {"http", "https"} or not configured.netloc:
        raise VoiceKycError("voice_kyc_redirect_not_configured")
    fallback = settings.voxly_frontend_url.rstrip("/") + "/"
    if not candidate:
        return fallback
    provided = urlsplit(str(candidate).strip())
    if (
        provided.scheme != configured.scheme
        or provided.netloc.lower() != configured.netloc.lower()
        or provided.username
        or provided.password
    ):
        raise VoiceKycError("invalid_voice_kyc_return_url", status_code=400)
    return str(candidate).strip()


async def _get_account(tenant_id: UUID) -> VobizSubaccount | None:
    factory = get_session_factory()
    if factory is None:
        raise VoiceKycError("database_required")
    async with factory() as session:
        return await session.get(VobizSubaccount, tenant_id)


def _carrier_setup_configured() -> bool:
    from server.services.vobiz_client import VobizClient

    if not _encryption_configured():
        return False
    try:
        return VobizClient().configured
    except Exception:
        return False


async def ensure_customer_subaccount(
    *, tenant_id: UUID, email: str, legal_name: str, business_type: str
) -> VobizSubaccount:
    from server.services.vobiz_client import VobizClient, VobizConfigError

    business_type = str(business_type or "").strip().lower()
    if business_type not in BUSINESS_TYPES:
        raise VoiceKycError("business_type_invalid", status_code=400)
    name = _safe_name(legal_name)
    email = str(email or "").strip().lower()
    if not email or len(email) > 320:
        raise VoiceKycError("account_email_required", status_code=400)
    # Validate encryption and parent credentials before creating durable or external state.
    _fernet()
    try:
        parent = VobizClient()
        if not parent.configured:
            raise VobizConfigError("Parent credentials unavailable")
    except VobizConfigError as exc:
        raise VoiceKycError("voice_service_not_configured") from exc

    factory = get_session_factory()
    if factory is None:
        raise VoiceKycError("database_required")
    async with factory() as session:
        tenant = await session.get(Tenant, tenant_id, with_for_update=True)
        if tenant is None:
            raise VoiceKycError("tenant_not_found", status_code=404)
        if tenant.status != "active":
            raise VoiceKycError("tenant_inactive", status_code=403)
        row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
        if row is not None:
            if row.provisioning_status in {"creating", "provisioning_unknown", "credentials_lost"}:
                raise VoiceKycError("voice_account_needs_review")
            if row.provisioning_status == "active":
                if row.business_type != business_type or row.account_name != name or row.account_email != email:
                    raise VoiceKycError("voice_identity_locked", status_code=409)
                return row
            # Only a definitive provider 4xx failure can be retried automatically.
            row.business_type = business_type
            row.account_name = name
            row.account_email = email
            row.provisioning_status = "creating"
            row.last_error_code = None
            row.updated_at = _utcnow()
        else:
            row = VobizSubaccount(
                tenant_id=tenant_id,
                business_type=business_type,
                account_name=name,
                account_email=email,
                provisioning_status="creating",
                kyc_status="not_started",
                kyc_calls_blocked=True,
                verifications={},
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(row)
        await session.commit()

    try:
        result = await parent.create_customer_subaccount(
            name=name,
            email=email,
            business_type=business_type,
            description=f"Tenant voice account {tenant_id}",
        )
    except Exception as exc:
        status = getattr(exc, "status", None)
        definitive = isinstance(status, int) and 400 <= status < 500 and status not in {408, 409, 429}
        async with factory() as session:
            row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
            if row is not None:
                row.provisioning_status = "failed" if definitive else "provisioning_unknown"
                row.last_error_code = f"provider_http_{status}" if definitive else "provider_result_unknown"
                row.updated_at = _utcnow()
                await session.commit()
        logger.warning("Tenant voice account creation failed tenant=%s error_type=%s", tenant_id, type(exc).__name__)
        raise VoiceKycError(
            "voice_account_create_failed" if definitive else "voice_account_needs_review"
        ) from exc

    account = result.get("sub_account") if isinstance(result, dict) else None
    credentials = result.get("auth_credentials") if isinstance(result, dict) else None
    if not isinstance(account, dict):
        account = {}
    if not isinstance(credentials, dict):
        credentials = account
    auth_id = str(credentials.get("auth_id") or account.get("auth_id") or "").strip()
    auth_token = str(credentials.get("auth_token") or account.get("auth_token") or "").strip()
    if (not auth_id.startswith("SA_") or not auth_token or any(c in auth_token for c in "*<>")
            or (account.get("auth_id") or account.get("id") or auth_id) != auth_id
            or account.get("kyc_mode", "customer_use") != "customer_use"):
        async with factory() as session:
            row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
            if row is not None:
                row.auth_id = auth_id or None
                row.provisioning_status = "credentials_lost"
                row.last_error_code = "provider_credentials_missing"
                row.updated_at = _utcnow()
                await session.commit()
        raise VoiceKycError("voice_account_needs_review")

    encrypted_token = encrypt_subaccount_token(tenant_id, auth_token)
    async with factory() as session:
        row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
        if row is None or row.provisioning_status != "creating":
            raise VoiceKycError("voice_account_needs_review")
        row.auth_id = auth_id
        row.parent_auth_id = parent.auth_id
        row.account_enabled = False  # confirmed by the parent's account lookup below
        row.encrypted_auth_token = encrypted_token
        row.provisioning_status = "active"
        row.kyc_status = "not_started"
        row.kyc_calls_blocked = True
        row.verifications = {}
        row.last_error_code = None
        row.updated_at = _utcnow()
        await session.commit()
        return row


async def start_kyc_session(
    *, tenant_id: UUID, email: str, legal_name: str, business_type: str, return_url: str | None
) -> dict:
    from server.config.urls import public_api_base
    from server.services.vobiz_client import VobizClient

    trusted_return_url = _trusted_return_url(return_url)
    webhook_url = public_api_base().rstrip("/") + "/api/webhooks/voice-kyc"
    if urlsplit(webhook_url).scheme != "https":
        raise VoiceKycError("voice_kyc_webhook_not_configured")
    account = await ensure_customer_subaccount(
        tenant_id=tenant_id,
        email=email,
        legal_name=legal_name,
        business_type=business_type,
    )
    status = await refresh_kyc_status(tenant_id, force=True)
    if status["approved"]:
        return {**status, "sessionUrl": None}
    parent = VobizClient()
    factory = get_session_factory()
    # Serialize link creation per tenant. This bounded provider request creates no
    # charges; a lost response is never retried inside the HTTP client.
    async with factory() as session:
        row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
        expires = _aware(row.kyc_session_expires_at)
        if (row.encrypted_kyc_url and expires and expires > _utcnow()
                and row.kyc_session_status not in {"failed", "expired", "revoked", "completed"}):
            return {**status, "sessionUrl": decrypt_subaccount_token(tenant_id, row.encrypted_kyc_url)}
        try:
            response = await parent.create_customer_kyc_session(
                sub_auth_id=str(account.auth_id), redirect_url=trusted_return_url, webhook_url=webhook_url,
            )
            session_url = str(response.get("widget_url") or "").strip()
            parsed = urlsplit(session_url)
            session_id = str(UUID(str(response.get("session_id") or "")))
            expires = datetime.fromisoformat(str(response.get("expires_at") or "").replace("Z", "+00:00"))
            if (parsed.scheme != "https" or parsed.hostname != "kyc.vobiz.ai"
                    or parsed.username or parsed.password or parsed.port not in (None, 443)
                    or response.get("account_auth_id") != account.auth_id
                    or expires.tzinfo is None or expires <= _utcnow()):
                raise ValueError("Invalid hosted verification session")
        except Exception as exc:
            logger.warning("Tenant voice KYC session failed tenant=%s error_type=%s", tenant_id, type(exc).__name__)
            raise VoiceKycError("voice_kyc_session_failed") from exc
        row.kyc_session_id = session_id
        row.encrypted_kyc_url = encrypt_subaccount_token(tenant_id, session_url)
        row.kyc_session_expires_at = expires
        row.kyc_session_status = "link_ready"
        await session.commit()
    return {**status, "sessionUrl": session_url}


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


async def refresh_kyc_status(tenant_id: UUID, *, force: bool = False) -> dict:
    from server.services.vobiz_client import VobizClient

    account = await _get_account(tenant_id)
    if account is None:
        return {
            "required": True,
            "configured": _carrier_setup_configured(),
            "approved": False,
            "status": "not_started",
            "callsBlocked": True,
            "verifications": {},
            "businessType": None,
            "legalName": "",
        }
    if account.provisioning_status != "active" or not account.auth_id or not account.encrypted_auth_token:
        return {
            "required": True,
            "configured": False,
            "approved": False,
            "status": account.provisioning_status,
            "callsBlocked": True,
            "verifications": {},
            "businessType": account.business_type,
            "legalName": account.account_name,
            "identityLocked": True,
        }

    now = _utcnow()
    last_sync = account.last_status_sync_at
    if last_sync and last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)
    if not force and last_sync and (now - last_sync).total_seconds() < _STATUS_CACHE_SECONDS:
        return _public_status(account)

    try:
        parent = VobizClient()
        if account.parent_auth_id != parent.auth_id:
            raise VoiceKycError("voice_parent_account_changed")
        identity = await parent.get_customer_subaccount(str(account.auth_id))
        if (identity.get("auth_id") != account.auth_id or identity.get("parent_auth_id") != parent.auth_id):
            raise VoiceKycError("voice_account_ownership_mismatch")
        enabled = identity.get("enabled") is True and identity.get("is_active") is True
        data = await parent.get_customer_kyc_status(str(account.auth_id))
    except Exception as exc:
        logger.warning("Tenant voice KYC status unavailable tenant=%s error_type=%s", tenant_id, type(exc).__name__)
        raise VoiceKycError("voice_kyc_status_unavailable") from exc
    blocked = data.get("kyc_calls_blocked") if isinstance(data, dict) else None
    mode = str(data.get("kyc_mode") or "").strip().lower() if isinstance(data, dict) else ""
    returned_id = str(data.get("sub_account_id") or "").strip() if isinstance(data, dict) else ""
    if (
        not isinstance(blocked, bool)
        or mode != "customer_use"
        or returned_id != account.auth_id
        or str(data.get("overall_status") or "").lower() not in _VERIFICATION_VALUES
        or data.get("business_type") != account.business_type
    ):
        raise VoiceKycError("voice_kyc_status_unavailable")
    status = str(data.get("overall_status") or "unknown").strip().lower()
    raw_verifications = data.get("verifications")
    verifications = {
        str(key).lower(): str(value).lower()
        for key, value in raw_verifications.items()
        if str(key).lower() in {"pan", "gst", "cin", "aadhaar"}
        and str(value).lower() in _VERIFICATION_VALUES
    } if isinstance(raw_verifications, dict) else {}
    factory = get_session_factory()
    async with factory() as session:
        row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
        if row is None:
            raise VoiceKycError("voice_account_needs_review")
        row.kyc_status = status[:32]
        row.account_enabled = enabled
        row.kyc_calls_blocked = blocked
        row.verifications = verifications
        row.last_status_sync_at = now
        row.last_error_code = None
        row.updated_at = now
        await session.commit()
        return _public_status(row)


def _public_status(account: VobizSubaccount) -> dict:
    return {
        "required": True,
        "configured": True,
        "approved": account.account_enabled is True and account.kyc_calls_blocked is False,
        "status": account.kyc_status if account.account_enabled else "account_disabled",
        "callsBlocked": not account.account_enabled or account.kyc_calls_blocked,
        "verifications": dict(account.verifications or {}),
        "businessType": account.business_type,
        "legalName": account.account_name,
        "identityLocked": True,
        "accountEnabled": account.account_enabled,
    }


def _encryption_configured() -> bool:
    try:
        _fernet()
    except VoiceKycError:
        return False
    return True


async def assert_voice_kyc_approved(tenant_id: UUID, *, action: str) -> None:
    try:
        status = await refresh_kyc_status(tenant_id, force=True)
    except VoiceKycError as exc:
        raise HTTPException(status_code=503, detail={"error": {
            "code": "voice_verification_unavailable", "message": "Phone service verification is temporarily unavailable. Please retry.",
        }}) from exc
    if status["approved"]:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": {
                "code": "voice_kyc_required",
                "message": f"Complete phone service verification before you {action}.",
                "kycStatus": status["status"],
                "verifyUrl": "/api/kyc/voice/session",
            }
        },
    )


async def vobiz_client_for_tenant(tenant_id: UUID):
    from server.services.vobiz_client import VobizClient

    account = await _get_account(tenant_id)
    if (
        account is None
        or account.provisioning_status != "active"
        or not account.auth_id
        or not account.encrypted_auth_token
    ):
        raise VoiceKycError("voice_account_not_ready")
    parent = VobizClient()
    if account.parent_auth_id != parent.auth_id:
        raise VoiceKycError("voice_parent_account_changed")
    token = decrypt_subaccount_token(tenant_id, account.encrypted_auth_token)
    return VobizClient(
        cfg={
            "auth_id": account.auth_id,
            "auth_token": token,
            "app_id": account.application_id or "",
            "phone_number": "",
            "disable_app_id": "true",
        }
    )


async def _number_account(tenant_id: UUID, e164: str):
    """Keep pre-existing platform-owned DIDs on their original carrier account."""
    from sqlalchemy import select

    from server.db.models.phase5_models import PhoneNumber

    factory = get_session_factory()
    if factory is None:
        raise VoiceKycError("database_required")
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.e164 == str(e164 or "").strip(),
                PhoneNumber.released_at.is_(None),
            )
        )
        number = result.scalar_one_or_none()
    if number is None or not number.carrier_number_id or number.status != "active":
        raise VoiceKycError("voice_number_not_owned", status_code=404)
    if number.vobiz_account_scope not in (None, "platform", "tenant"):
        raise VoiceKycError("voice_number_account_unknown")
    if number.vobiz_account_tenant_id and number.vobiz_account_scope != "tenant":
        raise VoiceKycError("voice_number_account_unknown")
    return number


async def vobiz_account_scope_for_number(tenant_id: UUID, e164: str) -> str:
    number = await _number_account(tenant_id, e164)
    return number.vobiz_account_scope or "platform"


async def vobiz_client_for_number(tenant_id: UUID, e164: str):
    from server.services.vobiz_client import VobizClient

    number = await _number_account(tenant_id, e164)
    scope = number.vobiz_account_scope or "platform"
    if scope == "tenant":
        owner = number.vobiz_account_tenant_id or number.tenant_id
        client = await vobiz_client_for_tenant(owner)
        client.account_tenant_id = str(owner)
        return client, scope
    return VobizClient(), scope


async def vobiz_client_for_call(meta: dict):
    """Credential choice is durable call metadata, never the current stack setting."""
    from server.services.vobiz_client import VobizClient

    scope = meta.get("vobiz_account_scope")
    if not scope:
        # Pre-subaccount calls may lack this field. A tenant that has a child
        # account makes missing scope ambiguous; never guess parent credentials.
        if meta.get("vobiz_account_tenant_id") or (meta.get("tenant_id") and await _get_account(UUID(str(meta["tenant_id"]))) is not None):
            raise VoiceKycError("voice_number_account_unknown")
        scope = "platform"
    if scope == "tenant":
        owner = meta.get("vobiz_account_tenant_id") or meta.get("tenant_id")
        if not owner:
            raise VoiceKycError("voice_account_not_ready")
        return await vobiz_client_for_tenant(UUID(str(owner)))
    if scope != "platform":
        raise VoiceKycError("voice_number_account_unknown")
    return VobizClient()


async def provision_tenant_number(tenant_id: UUID, e164: str) -> dict:
    """Direct child purchase is documented and billed to the parent account."""
    await assert_voice_kyc_approved(tenant_id, action="activate a phone number")
    client = await vobiz_client_for_tenant(tenant_id)
    factory = get_session_factory()
    async with factory() as session:
        account = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
        app_id = await client.ensure_default_application(name=f"tenant_{tenant_id.hex}", app_id=account.application_id)
        account.application_id = app_id
        await session.commit()
    # The account's default application is set BEFORE the DID is created.
    result = await client.place_number_order(e164)
    number_id = str(result.get("id") or "").strip()
    if not number_id:
        raise VoiceKycError("voice_number_confirmation_pending")
    return {"phone_number_id": number_id}


def verify_voice_webhook(raw: bytes, signature: str) -> None:
    from server.services.vobiz_client import VobizClient

    try:
        secret = VobizClient().cfg["auth_token"]
    except Exception as exc:
        raise VoiceKycError("voice_service_not_configured") from exc
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(signature or "")):
        raise VoiceKycError("bad_signature", status_code=401)


async def apply_voice_webhook(payload: dict) -> dict:
    """A signed callback is a refresh hint, never evidence of KYC approval."""
    events = {"kyc.initiated", "kyc.submitted", "kyc.completed", "kyc.failed", "kyc.session_expired", "kyc.session_revoked"}
    if payload.get("event") not in events:
        return {"ok": True, "ignored": True}
    factory = get_session_factory()
    if factory is None:
        raise VoiceKycError("database_required")
    async with factory() as session:
        account = (await session.execute(select(VobizSubaccount).where(
            VobizSubaccount.auth_id == str(payload.get("account_auth_id") or ""),
        ).with_for_update())).scalar_one_or_none()
        if account is None or account.kyc_session_id != str(payload.get("session_id") or ""):
            return {"ok": True, "ignored": True}
        tenant_id = account.tenant_id
        status = str(payload["event"]).removeprefix("kyc.").removeprefix("session_")
        # Terminal events invalidate the hosted link. Replays and out-of-order
        # initiation/submission events cannot make a completed link reusable.
        if status in {"completed", "failed", "expired", "revoked"}:
            account.kyc_session_status = status
            account.encrypted_kyc_url = None
        account.last_status_sync_at = None
        await session.commit()
    await refresh_kyc_status(tenant_id, force=True)
    return {"ok": True}
