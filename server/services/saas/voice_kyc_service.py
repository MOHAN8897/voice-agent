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
from sqlalchemy import desc, select

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
_TRUSTED_PRODUCTION_CONSOLE_ORIGINS = frozenset({
    "https://www.dialtact.com",
    "https://dialtact.com",
    "https://app.dialtact.com",
    "https://app-dev.dialtact.com",
    "https://app-dev.hustlelabs.in",
})


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
    try:
        configured = urlsplit(str(settings.voxly_frontend_url or "").strip())
        configured_port = configured.port
    except ValueError as exc:
        raise VoiceKycError("voice_kyc_redirect_not_configured") from exc
    if configured.scheme not in {"http", "https"} or not configured.hostname:
        raise VoiceKycError("voice_kyc_redirect_not_configured")
    fallback = settings.voxly_frontend_url.rstrip("/") + "/"
    if not candidate:
        return fallback
    candidate = str(candidate).strip()
    try:
        provided = urlsplit(candidate)
        provided_port = provided.port
    except ValueError as exc:
        raise VoiceKycError("invalid_voice_kyc_return_url", status_code=400) from exc
    if provided.username or provided.password:
        raise VoiceKycError("invalid_voice_kyc_return_url", status_code=400)
    default_ports = {"http": 80, "https": 443}
    configured_scheme = configured.scheme.lower()
    provided_scheme = provided.scheme.lower()
    configured_effective_port = (
        configured_port if configured_port is not None else default_ports.get(configured_scheme)
    )
    provided_effective_port = (
        provided_port if provided_port is not None else default_ports.get(provided_scheme)
    )
    configured_origin = (configured_scheme, configured.hostname.lower(), configured_effective_port)
    provided_origin = (provided_scheme, (provided.hostname or "").lower(), provided_effective_port)
    if provided_origin == configured_origin:
        return candidate

    # The Vite console runs on loopback during local development while the
    # configured canonical console URL may point at app-dev. Permit only the
    # known local console ports in development; never widen production redirects.
    if (
        settings.app_environment == "development"
        and provided_scheme == "http"
        and provided.hostname in {"localhost", "127.0.0.1"}
        and provided_port in {None, 3000, 5173}
    ):
        return candidate
    provided_host = (provided.hostname or "").lower()
    provided_host_origin = f"{provided_scheme}://{provided_host}"
    if (
        provided_scheme == "https"
        and provided_port in {None, 443}
        and provided_host_origin in _TRUSTED_PRODUCTION_CONSOLE_ORIGINS
    ):
        return candidate
    raise VoiceKycError("invalid_voice_kyc_return_url", status_code=400)


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


def _alias_email(email: str, tenant_id: UUID) -> str:
    parts = email.split("@", 1)
    local = parts[0].split("+", 1)[0]
    domain = parts[1] if len(parts) > 1 else "dialtact.com"
    return f"{local}+voice-{str(tenant_id)[:8]}@{domain}"


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
                if row.business_type != business_type or row.account_name != name:
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
        try:
            result = await parent.create_customer_subaccount(
                name=name,
                email=email,
                business_type=business_type,
                description=f"Tenant voice account {tenant_id}",
            )
        except Exception as exc:
            status = getattr(exc, "status", None)
            body = getattr(exc, "body", "")
            is_email_conflict = (
                isinstance(status, int)
                and status == 409
                and ("already in use" in str(body).lower() or "already in use" in str(exc).lower())
            )
            if is_email_conflict:
                aliased = _alias_email(email, tenant_id)
                if aliased.lower() != email.lower():
                    logger.info(
                        "Subaccount email conflict tenant=%s, retrying with aliased email=%s",
                        tenant_id,
                        aliased,
                    )
                    email = aliased
                    result = await parent.create_customer_subaccount(
                        name=name,
                        email=email,
                        business_type=business_type,
                        description=f"Tenant voice account {tenant_id}",
                    )
                else:
                    raise
            else:
                raise
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
        # Hosted KYC supports polling without callbacks. Never send an insecure webhook URL.
        webhook_url = None
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
        if (status["status"] != "failed" and row.encrypted_kyc_url and expires and expires > _utcnow()
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
        carrier_ready = _carrier_setup_configured()
        is_sub_active = account.provisioning_status == "active" and bool(account.auth_id)
        computed_status = (
            "not_started"
            if account.auth_id is None and account.provisioning_status not in {"creating", "failed"}
            else account.provisioning_status
        )
        return {
            "required": True,
            "configured": carrier_ready,
            "approved": False,
            "status": computed_status,
            "callsBlocked": True,
            "verifications": {},
            "businessType": account.business_type,
            "legalName": account.account_name,
            "identityLocked": is_sub_active,
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

    # Vobiz live API returns kyc_calls_blocked and kyc_mode in subaccount (identity),
    # while test fixtures / mocks may supply them in data (get_customer_kyc_status). Support both.
    if isinstance(data, dict) and "kyc_calls_blocked" in data:
        blocked = data["kyc_calls_blocked"]
    elif isinstance(identity, dict) and "kyc_calls_blocked" in identity:
        blocked = identity["kyc_calls_blocked"]
    else:
        blocked = None

    mode = str(data.get("kyc_mode") or (identity.get("kyc_mode") if isinstance(identity, dict) else "") or "").strip().lower()
    returned_id = str(data.get("sub_account_id") or data.get("auth_id") or (identity.get("auth_id") if isinstance(identity, dict) else "") or "").strip()
    raw_status = str(data.get("overall_status") or data.get("kyc_status") or (identity.get("kyc_status") if isinstance(identity, dict) else "") or "pending").strip().lower()
    b_type = data.get("business_type") or (identity.get("business_type") if isinstance(identity, dict) else None)

    if (
        not isinstance(blocked, bool)
        or mode != "customer_use"
        or returned_id != account.auth_id
        or (raw_status not in _VERIFICATION_VALUES and raw_status not in {"in_review", "approved"})
        or (b_type and b_type != account.business_type)
    ):
        logger.warning(
            "Voice KYC status validation failed tenant=%s blocked=%s mode=%s returned_id=%s raw_status=%s b_type=%s",
            tenant_id, blocked, mode, returned_id, raw_status, b_type,
        )
        raise VoiceKycError("voice_kyc_status_unavailable")

    status = "verified" if raw_status in {"verified", "approved"} else raw_status
    if status not in _VERIFICATION_VALUES:
        status = "pending"

    raw_verifications = data.get("verifications") if isinstance(data, dict) else None
    if isinstance(raw_verifications, dict):
        verifications = {
            str(key).lower(): str(value).lower()
            for key, value in raw_verifications.items()
            if str(key).lower() in {"pan", "gst", "cin", "aadhaar"}
            and str(value).lower() in _VERIFICATION_VALUES
        }
    else:
        verifications = {}
        if isinstance(data, dict):
            for doc in ("pan", "gst", "cin", "aadhaar"):
                val = data.get(f"{doc}_status")
                if val and str(val).lower() in _VERIFICATION_VALUES:
                    verifications[doc] = str(val).lower()

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
        "configured": _carrier_setup_configured(),
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
    from server.services.telephony import active_telephony_provider

    if active_telephony_provider() != "vobiz":
        return
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


async def admin_set_voice_kyc_status(
    tenant_id: UUID,
    *,
    status: str,
    actor: str,
    reason: str,
) -> dict:
    """Manual ops / dev override for voice KYC verification status."""
    status = str(status or "").strip().lower()
    if status == "approved":
        status = "verified"
    elif status in {"declined", "rejected"}:
        status = "failed"
    elif status in {"in_review", "in review"}:
        status = "pending"
    if status not in {"verified", "pending", "failed", "not_started"}:
        raise VoiceKycError("invalid_status", status_code=400)
    reason = str(reason or "").strip()
    if len(reason) < 8:
        raise VoiceKycError("statement_required", status_code=400)
    factory = get_session_factory()
    if factory is None:
        raise VoiceKycError("database_required")
    async with factory() as session:
        row = await session.get(VobizSubaccount, tenant_id, with_for_update=True)
        if row is None:
            raise VoiceKycError("voice_account_not_found", status_code=404)
        if status == "verified":
            row.kyc_status = "verified"
            row.kyc_calls_blocked = False
            row.account_enabled = True
            row.provisioning_status = "active"
            row.verifications = {"pan": "verified", "aadhaar": "verified"}
        elif status == "failed":
            row.kyc_status = "failed"
            row.kyc_calls_blocked = True
            row.verifications = {}
        elif status == "pending":
            row.kyc_status = "pending"
            row.kyc_calls_blocked = True
        elif status == "not_started":
            row.kyc_status = "not_started"
            row.kyc_calls_blocked = True
            row.verifications = {}
        row.last_status_sync_at = _utcnow()
        row.updated_at = _utcnow()
        await session.commit()
        return _public_status(row)


async def list_voice_verifications(status: str | None = None) -> list[dict]:
    """List tenant carrier subaccount KYC records for platform ops / admin panel."""
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        query = (
            select(VobizSubaccount, Tenant)
            .join(Tenant, Tenant.tenant_id == VobizSubaccount.tenant_id)
            .where(Tenant.deleted_at.is_(None))
            .order_by(desc(VobizSubaccount.updated_at))
        )
        if status:
            status_clean = str(status).strip().lower()
            if status_clean in {"approved", "verified"}:
                query = query.where(
                    VobizSubaccount.kyc_status == "verified",
                    VobizSubaccount.kyc_calls_blocked.is_(False),
                )
            elif status_clean in {"pending", "in review", "in_review"}:
                query = query.where(VobizSubaccount.kyc_status.in_(["pending", "link_ready"]))
            elif status_clean in {"failed", "declined"}:
                query = query.where(VobizSubaccount.kyc_status.in_(["failed", "revoked", "expired"]))
        rows = (await session.execute(query.limit(200))).all()

    verifications = []
    for sub, t in rows:
        is_approved = (
            sub.kyc_status == "verified" and not sub.kyc_calls_blocked and sub.account_enabled
        )
        is_in_review = sub.kyc_status in ("pending", "link_ready") or (
            sub.kyc_status == "verified" and sub.kyc_calls_blocked
        )
        is_declined = sub.kyc_status in ("failed", "revoked", "expired")
        status_label = (
            "Approved"
            if is_approved
            else ("In Review" if is_in_review else ("Declined" if is_declined else "Not Started"))
        )

        verifications.append({
            "tenantId": str(sub.tenant_id),
            "tenantName": t.name,
            "legalName": sub.account_name,
            "accountEmail": sub.account_email,
            "businessType": sub.business_type,
            "status": status_label,
            "rawKycStatus": sub.kyc_status,
            "approved": is_approved,
            "callsBlocked": sub.kyc_calls_blocked,
            "provisioningStatus": sub.provisioning_status,
            "verifications": sub.verifications or {},
            "subaccountAuthId": sub.auth_id,
            "updatedAt": sub.updated_at.isoformat() if sub.updated_at else None,
            "createdAt": sub.created_at.isoformat() if sub.created_at else None,
        })
    return verifications


