"""Stored platform-admin accounts: invite, roles, suspension, removal, sign-in.

Who this is for: the people who operate the admin portal. Customer users and the
console-side platform admins (SAAS_PLATFORM_ADMIN_EMAILS) are different things and
are not managed here.

Safeguards enforced here, not in the UI:

* every change needs a written reason and is written to the activity log;
* nobody can change their own role, suspend, reset or remove themselves;
* the last active stored super admin cannot be demoted, suspended or removed;
* sensitive changes need the target's username typed back as confirmation;
* invite and reset links are single-use, stored only as SHA-256 hashes, and
  expire (72 hours for invites, 24 hours for resets);
* passwords are chosen by the admin through that link and stored as PBKDF2; no
  password is ever generated, returned or logged;
* suspension, removal, password reset and "sign out everywhere" bump the
  account's session epoch, which ends every session it holds within seconds.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from server.auth import rbac
from server.auth.admin_roles import ASSIGNABLE_ROLES, ROLE_LABELS
from server.auth.admin_sessions import AccountSessionState, account_ref, parse_account_ref, refresh
from server.auth.passwords import hash_portal_password, verify_portal_password
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.platform_admin_models import PlatformAdminAccount
from server.services.saas.admin_audit import record_admin_action

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "platform_admin"
INVITE_TTL = timedelta(hours=72)
RESET_TTL = timedelta(hours=24)
MIN_PASSWORD_LENGTH = 12
MIN_REASON_LENGTH = 5

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_DUMMY_HASH = "pbkdf2-sha256$600000$" + "00" * 16 + "$" + "00" * 32


class AdminAccountError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Actor:
    """Who is making a change: a stored account, or the built-in env login."""

    subject: str
    role: str
    account_id: str | None = None

    @classmethod
    def from_session(cls, session: Any) -> "Actor":
        parsed = parse_account_ref(getattr(session, "account_ref", None))
        return cls(
            subject=str(getattr(session, "subject", "") or "unknown"),
            role=str(getattr(session, "role", "") or ""),
            account_id=parsed[0] if parsed else None,
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _factory():
    factory = get_session_factory()
    if factory is None:
        raise AdminAccountError("db_unavailable", "A database is required to manage admins.", 503)
    return factory


def builtin_username() -> str | None:
    settings = get_settings()
    if settings.dev_portal_username and settings.dev_portal_password:
        return settings.dev_portal_username.strip()
    return None


def session_ref(account: PlatformAdminAccount) -> str:
    return account_ref(account.id, account.session_epoch)


# --------------------------------------------------------------------------- validation


def _clean_reason(reason: str | None) -> str:
    text = " ".join(str(reason or "").split())
    if len(text) < MIN_REASON_LENGTH:
        raise AdminAccountError("reason_required", f"Give a reason of at least {MIN_REASON_LENGTH} characters.")
    return text[:500]


def _clean_email(email: str | None) -> str:
    value = str(email or "").strip().lower()
    if len(value) > 320 or not _EMAIL_RE.match(value):
        raise AdminAccountError("invalid_email", "Enter a valid email address.")
    return value


def _clean_username(username: str | None, email: str) -> str:
    raw = str(username or "").strip().lower()
    if not raw:
        raw = re.sub(r"[^a-z0-9._-]", ".", email.split("@", 1)[0]).strip(".-_")
        raw = raw[:64]
        if len(raw) < 3:
            raw = (raw + "-admin")[:64]
    if not _USERNAME_RE.match(raw):
        raise AdminAccountError(
            "invalid_username",
            "Usernames are 3–64 characters: lowercase letters, digits, dots, dashes or underscores.",
        )
    builtin = builtin_username()
    if builtin and builtin.casefold() == raw.casefold():
        raise AdminAccountError("username_taken", "That username is reserved for the built-in login.", 409)
    return raw


def _clean_role(role: str | None) -> str:
    value = str(role or "").strip()
    if value not in ASSIGNABLE_ROLES:
        raise AdminAccountError("invalid_role", "Choose one of the listed roles.")
    return value


def _check_confirm(account: PlatformAdminAccount, confirm: str | None) -> None:
    if str(confirm or "").strip().casefold() != account.username.casefold():
        raise AdminAccountError(
            "confirmation_required",
            f"Type the admin's username ({account.username}) to confirm.",
        )


def _check_password(password: str, account: PlatformAdminAccount) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminAccountError("weak_password", f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > 200:
        raise AdminAccountError("weak_password", "Use at most 200 characters.")
    lowered = password.casefold()
    local = account.email.split("@", 1)[0].casefold()
    if account.username.casefold() in lowered or (len(local) >= 3 and local in lowered):
        raise AdminAccountError("weak_password", "The password must not contain your username or email.")
    if len(set(password)) < 6:
        raise AdminAccountError("weak_password", "The password is too repetitive.")


# --------------------------------------------------------------------------- serialization


def _invite_state(account: PlatformAdminAccount, now: datetime) -> str | None:
    if not account.invite_token_hash or not account.invite_expires_at:
        return None
    return "expired" if _aware(account.invite_expires_at) <= now else "pending"


def serialize(account: PlatformAdminAccount, *, actor: Actor | None = None, last_super: bool = False) -> dict[str, Any]:
    now = _utcnow()
    invite_state = _invite_state(account, now)
    return {
        "id": str(account.id),
        "username": account.username,
        "email": account.email,
        "fullName": account.full_name or "",
        "role": account.role,
        "roleLabel": ROLE_LABELS.get(account.role, account.role),
        "status": account.status,
        "statusReason": account.status_reason,
        "hasPassword": bool(account.password_hash),
        "link": (
            {
                "purpose": account.invite_purpose or "invite",
                "state": invite_state,
                "expiresAt": _iso(account.invite_expires_at),
                "sentAt": _iso(account.invite_sent_at),
            }
            if invite_state
            else None
        ),
        "lastSignInAt": _iso(account.last_sign_in_at),
        "lastSignInIp": account.last_sign_in_ip,
        "passwordChangedAt": _iso(account.password_changed_at),
        "createdAt": _iso(account.created_at),
        "createdBy": account.created_by or "",
        "updatedAt": _iso(account.updated_at),
        "updatedBy": account.updated_by,
        "isSelf": bool(actor and actor.account_id == str(account.id)),
        "isLastSuperAdmin": last_super,
        "mfa": None,
    }


# --------------------------------------------------------------------------- reads


async def store_status() -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        return {"ready": False, "reason": "No database is configured, so only the built-in login can sign in."}
    try:
        async with factory() as db:
            await db.execute(select(func.count()).select_from(PlatformAdminAccount))
    except Exception:
        return {
            "ready": False,
            "reason": "The admin accounts table is missing. Run the database migrations (051_platform_admin_accounts).",
        }
    return {"ready": True, "reason": None}


async def load_session_states() -> list[AccountSessionState] | None:
    """Every account's session state for the revocation snapshot. None without a DB."""
    factory = get_session_factory()
    if factory is None:
        return None
    try:
        async with factory() as db:
            rows = (await db.execute(select(PlatformAdminAccount))).scalars().all()
    except Exception as exc:
        # Missing table (migration not run) means no stored accounts can exist.
        if "platform_admin_accounts" in str(exc).lower() or "no such table" in str(exc).lower():
            return []
        raise
    return [
        AccountSessionState(
            account_id=str(r.id),
            username=r.username,
            role=r.role,
            status=r.status,
            session_epoch=int(r.session_epoch or 0),
        )
        for r in rows
    ]


async def any_accounts() -> bool:
    factory = get_session_factory()
    if factory is None:
        return False
    try:
        async with factory() as db:
            count = await db.scalar(
                select(func.count()).select_from(PlatformAdminAccount).where(PlatformAdminAccount.status == "active")
            )
    except Exception:
        return False
    return bool(count)


async def _active_super_ids(db, *, lock: bool = False) -> set[str]:
    stmt = select(PlatformAdminAccount.id).where(
        PlatformAdminAccount.role == rbac.ROLE_SUPER_ADMIN, PlatformAdminAccount.status == "active"
    )
    if lock:
        stmt = stmt.with_for_update()
    return {str(i) for i in (await db.execute(stmt)).scalars().all()}


async def list_accounts(actor: Actor) -> list[dict[str, Any]]:
    async with _factory()() as db:
        rows = (
            await db.execute(
                select(PlatformAdminAccount)
                .where(PlatformAdminAccount.status != "removed")
                .order_by(PlatformAdminAccount.created_at.asc())
            )
        ).scalars().all()
        supers = await _active_super_ids(db)
    last = next(iter(supers)) if len(supers) == 1 else None
    return [serialize(r, actor=actor, last_super=str(r.id) == last) for r in rows]


async def _load(db, account_id: str, *, lock: bool = True) -> PlatformAdminAccount:
    try:
        uid = uuid.UUID(str(account_id))
    except (TypeError, ValueError):
        raise AdminAccountError("not_found", "Admin not found.", 404)
    stmt = select(PlatformAdminAccount).where(PlatformAdminAccount.id == uid)
    if lock:
        stmt = stmt.with_for_update()
    account = (await db.execute(stmt)).scalar_one_or_none()
    if account is None or account.status == "removed":
        raise AdminAccountError("not_found", "Admin not found.", 404)
    return account


# --------------------------------------------------------------------------- guards


def _forbid_self(actor: Actor, account: PlatformAdminAccount, what: str) -> None:
    if actor.account_id and actor.account_id == str(account.id):
        raise AdminAccountError("self_change", f"You can't {what} your own account. Ask another super admin.", 403)


async def _forbid_last_super(db, account: PlatformAdminAccount, what: str) -> None:
    if account.role != rbac.ROLE_SUPER_ADMIN or account.status != "active":
        return
    supers = await _active_super_ids(db, lock=True)
    if supers - {str(account.id)}:
        return
    raise AdminAccountError(
        "last_super_admin",
        f"This is the last active super admin, so you can't {what} them. Make someone else a super admin first.",
        409,
    )


async def _audit(actor: Actor, action: str, account: PlatformAdminAccount, payload: dict, request: Any) -> None:
    await record_admin_action(
        actor=actor.subject,
        action=f"platform_admin.{action}",
        resource_type=RESOURCE_TYPE,
        resource_id=str(account.id),
        payload={"username": account.username, "email": account.email, **payload},
        request=request,
    )


def _issue_link(account: PlatformAdminAccount, purpose: str) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires = _utcnow() + (INVITE_TTL if purpose == "invite" else RESET_TTL)
    account.invite_token_hash = _hash_token(raw)
    account.invite_purpose = purpose
    account.invite_expires_at = expires
    account.invite_sent_at = _utcnow()
    return raw, expires


def _clear_link(account: PlatformAdminAccount) -> None:
    account.invite_token_hash = None
    account.invite_purpose = None
    account.invite_expires_at = None


def link_path(raw_token: str) -> str:
    return f"/dev/login/invite?token={raw_token}"


async def _deliver_link(
    account: PlatformAdminAccount, raw: str, purpose: str, inviter: str, portal_origin: str | None
) -> dict[str, Any]:
    """Email the link when an origin and an email provider are available."""
    origin = _clean_origin(portal_origin)
    if not origin:
        return {"emailed": False, "emailNote": "No portal address was supplied, so share the link yourself."}
    try:
        from server.services.saas.email_service import _email_shell, send_email
    except Exception:
        return {"emailed": False, "emailNote": "Email is not available on this server."}
    url = origin + link_path(raw)
    hours = int((INVITE_TTL if purpose == "invite" else RESET_TTL).total_seconds() // 3600)
    if purpose == "invite":
        subject = "You've been invited to the DialTact admin portal"
        lines = (
            f"{inviter} invited you to the DialTact admin portal as {ROLE_LABELS.get(account.role, account.role)}.",
            f"Your username is <b>{account.username}</b>. Choose a password to finish. "
            f"The link works once and expires in {hours} hours.",
        )
        cta = "Set your password"
    else:
        subject = "Reset your DialTact admin password"
        lines = (
            f"{inviter} reset your DialTact admin portal password.",
            f"Choose a new password. The link works once and expires in {hours} hours.",
        )
        cta = "Choose a new password"
    result = await send_email(account.email, subject, _email_shell(*lines, cta_label=cta, cta_url=url))
    if result.ok:
        return {"emailed": True, "emailNote": f"Emailed to {account.email}."}
    return {"emailed": False, "emailNote": f"Email not sent ({result.code}). Share the link yourself."}


def _clean_origin(origin: str | None) -> str | None:
    value = str(origin or "").strip().rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.\-\[\]:]+", value):
        return value
    return None


# --------------------------------------------------------------------------- writes


async def invite(
    actor: Actor,
    *,
    email: str,
    full_name: str | None,
    username: str | None,
    role: str,
    reason: str,
    portal_origin: str | None = None,
    request: Any = None,
) -> dict[str, Any]:
    reason = _clean_reason(reason)
    email = _clean_email(email)
    username = _clean_username(username, email)
    role = _clean_role(role)
    name = " ".join(str(full_name or "").split())[:255]
    async with _factory()() as db:
        clash = (
            await db.execute(
                select(PlatformAdminAccount).where(
                    or_(
                        func.lower(PlatformAdminAccount.email) == email,
                        func.lower(PlatformAdminAccount.username) == username,
                    )
                )
            )
        ).scalars().first()
        if clash is not None:
            field = "email" if clash.email.lower() == email else "username"
            raise AdminAccountError(f"{field}_taken", f"An admin with that {field} already exists.", 409)
        account = PlatformAdminAccount(
            id=uuid.uuid4(),
            username=username,
            email=email,
            full_name=name,
            role=role,
            status="invited",
            password_hash="",
            session_epoch=1,
            created_by=actor.subject,
            created_at=_utcnow(),
            updated_at=_utcnow(),
            updated_by=actor.subject,
        )
        raw, expires = _issue_link(account, "invite")
        db.add(account)
        await db.commit()
    await _audit(actor, "invite", account, {"role": role, "reason": reason, "expiresAt": _iso(expires)}, request)
    await refresh(force=True)
    delivery = await _deliver_link(account, raw, "invite", actor.subject, portal_origin)
    return {
        "admin": serialize(account, actor=actor),
        "link": {"path": link_path(raw), "expiresAt": _iso(expires), "purpose": "invite", **delivery},
    }


async def resend_invite(
    actor: Actor, account_id: str, *, reason: str, portal_origin: str | None = None, request: Any = None
) -> dict[str, Any]:
    reason = _clean_reason(reason)
    async with _factory()() as db:
        account = await _load(db, account_id)
        if account.status != "invited":
            raise AdminAccountError("not_invited", "Only admins who haven't accepted their invite can be re-invited.", 409)
        raw, expires = _issue_link(account, "invite")
        account.updated_by = actor.subject
        await db.commit()
    await _audit(actor, "invite_resent", account, {"reason": reason, "expiresAt": _iso(expires)}, request)
    delivery = await _deliver_link(account, raw, "invite", actor.subject, portal_origin)
    return {
        "admin": serialize(account, actor=actor),
        "link": {"path": link_path(raw), "expiresAt": _iso(expires), "purpose": "invite", **delivery},
    }


async def change_role(
    actor: Actor, account_id: str, *, role: str, reason: str, confirm: str | None = None, request: Any = None
) -> dict[str, Any]:
    reason = _clean_reason(reason)
    role = _clean_role(role)
    async with _factory()() as db:
        account = await _load(db, account_id)
        _forbid_self(actor, account, "change the role of")
        before = account.role
        if before == role:
            raise AdminAccountError("no_change", "The admin already has that role.", 409)
        if rbac.ROLE_SUPER_ADMIN in (before, role):
            _check_confirm(account, confirm)
        if before == rbac.ROLE_SUPER_ADMIN:
            await _forbid_last_super(db, account, "demote")
        account.role = role
        account.updated_by = actor.subject
        await db.commit()
    await _audit(actor, "role_changed", account, {"from": before, "to": role, "reason": reason}, request)
    await refresh(force=True)
    return {"admin": serialize(account, actor=actor)}


async def suspend(actor: Actor, account_id: str, *, reason: str, confirm: str | None, request: Any = None) -> dict[str, Any]:
    reason = _clean_reason(reason)
    async with _factory()() as db:
        account = await _load(db, account_id)
        _forbid_self(actor, account, "suspend")
        _check_confirm(account, confirm)
        if account.status == "suspended":
            raise AdminAccountError("no_change", "The admin is already suspended.", 409)
        await _forbid_last_super(db, account, "suspend")
        before = account.status
        account.status = "suspended"
        account.status_reason = reason
        account.session_epoch = int(account.session_epoch or 0) + 1
        _clear_link(account)
        account.updated_by = actor.subject
        await db.commit()
    await _audit(actor, "suspended", account, {"from": before, "reason": reason}, request)
    await refresh(force=True)
    return {"admin": serialize(account, actor=actor)}


async def reactivate(actor: Actor, account_id: str, *, reason: str, request: Any = None) -> dict[str, Any]:
    reason = _clean_reason(reason)
    async with _factory()() as db:
        account = await _load(db, account_id)
        _forbid_self(actor, account, "reactivate")
        if account.status != "suspended":
            raise AdminAccountError("no_change", "Only suspended admins can be reactivated.", 409)
        # An admin suspended before choosing a password goes back to "invited".
        account.status = "active" if account.password_hash else "invited"
        account.status_reason = None
        account.updated_by = actor.subject
        await db.commit()
    await _audit(actor, "reactivated", account, {"to": account.status, "reason": reason}, request)
    await refresh(force=True)
    return {"admin": serialize(account, actor=actor)}


async def remove(actor: Actor, account_id: str, *, reason: str, confirm: str | None, request: Any = None) -> dict[str, Any]:
    reason = _clean_reason(reason)
    async with _factory()() as db:
        account = await _load(db, account_id)
        _forbid_self(actor, account, "remove")
        _check_confirm(account, confirm)
        await _forbid_last_super(db, account, "remove")
        identity = {"username": account.username, "email": account.email, "role": account.role}
        tag = account.id.hex[:8]
        # Free the username and email for reuse; the audit row keeps the original.
        account.username = f"removed.{tag}.{account.username}"[:64]
        account.email = f"removed+{account.id.hex}@invalid.local"
        account.status = "removed"
        account.password_hash = ""
        account.session_epoch = int(account.session_epoch or 0) + 1
        _clear_link(account)
        account.removed_at = _utcnow()
        account.status_reason = reason
        account.updated_by = actor.subject
        await db.commit()
    await record_admin_action(
        actor=actor.subject,
        action="platform_admin.removed",
        resource_type=RESOURCE_TYPE,
        resource_id=str(account.id),
        payload={**identity, "reason": reason},
        request=request,
    )
    await refresh(force=True)
    return {"ok": True, "id": str(account.id)}


async def sign_out_everywhere(actor: Actor, account_id: str, *, reason: str, request: Any = None) -> dict[str, Any]:
    reason = _clean_reason(reason)
    async with _factory()() as db:
        account = await _load(db, account_id)
        account.session_epoch = int(account.session_epoch or 0) + 1
        account.updated_by = actor.subject
        await db.commit()
    await _audit(actor, "signed_out", account, {"reason": reason}, request)
    await refresh(force=True)
    return {"admin": serialize(account, actor=actor)}


async def reset_password(
    actor: Actor,
    account_id: str,
    *,
    reason: str,
    confirm: str | None,
    portal_origin: str | None = None,
    request: Any = None,
) -> dict[str, Any]:
    """Invalidate the current password, end all sessions, and issue a one-time reset link."""
    reason = _clean_reason(reason)
    async with _factory()() as db:
        account = await _load(db, account_id)
        _forbid_self(actor, account, "reset the password of")
        _check_confirm(account, confirm)
        if account.status != "active":
            raise AdminAccountError(
                "not_active",
                "Only active admins have a password to reset. Re-send the invite or reactivate them first.",
                409,
            )
        account.password_hash = ""
        account.session_epoch = int(account.session_epoch or 0) + 1
        raw, expires = _issue_link(account, "reset")
        account.updated_by = actor.subject
        await db.commit()
    await _audit(actor, "password_reset", account, {"reason": reason, "expiresAt": _iso(expires)}, request)
    await refresh(force=True)
    delivery = await _deliver_link(account, raw, "reset", actor.subject, portal_origin)
    return {
        "admin": serialize(account, actor=actor),
        "link": {"path": link_path(raw), "expiresAt": _iso(expires), "purpose": "reset", **delivery},
    }


# --------------------------------------------------------------------------- invite links (public)


async def _by_token(db, raw: str) -> PlatformAdminAccount:
    token = str(raw or "").strip()
    if not token or len(token) > 200:
        raise AdminAccountError("invalid_link", "This link is not valid.", 400)
    account = (
        await db.execute(
            select(PlatformAdminAccount).where(PlatformAdminAccount.invite_token_hash == _hash_token(token))
        )
    ).scalar_one_or_none()
    if account is None or account.status in ("removed", "suspended"):
        raise AdminAccountError("invalid_link", "This link is not valid or has already been used.", 400)
    if not account.invite_expires_at or _aware(account.invite_expires_at) <= _utcnow():
        raise AdminAccountError("link_expired", "This link has expired. Ask a super admin for a new one.", 410)
    return account


async def inspect_link(raw: str) -> dict[str, Any]:
    async with _factory()() as db:
        account = await _by_token(db, raw)
    return {
        "purpose": account.invite_purpose or "invite",
        "username": account.username,
        "email": account.email,
        "fullName": account.full_name or "",
        "roleLabel": ROLE_LABELS.get(account.role, account.role),
        "expiresAt": _iso(account.invite_expires_at),
        "minPasswordLength": MIN_PASSWORD_LENGTH,
    }


async def accept_link(raw: str, password: str, request: Any = None) -> dict[str, Any]:
    async with _factory()() as db:
        account = await _by_token(db, raw)
        _check_password(str(password or ""), account)
        account.password_hash = await asyncio.to_thread(hash_portal_password, str(password))
        purpose = account.invite_purpose or "invite"
        account.status = "active"
        account.password_changed_at = _utcnow()
        account.session_epoch = int(account.session_epoch or 0) + 1
        _clear_link(account)
        account.updated_by = account.username
        await db.commit()
    actor = Actor(subject=account.username, role=account.role, account_id=str(account.id))
    await _audit(actor, "invite_accepted" if purpose == "invite" else "password_set", account, {}, request)
    await refresh(force=True)
    return {"ok": True, "username": account.username}


# --------------------------------------------------------------------------- sign-in


async def authenticate(
    login: str, password: str, *, ip: str | None = None, request: Any = None
) -> PlatformAdminAccount | None:
    """The active account for this username/email and password, else None."""
    value = str(login or "").strip().lower()
    factory = get_session_factory()
    if factory is None or not value or not password:
        return None
    try:
        async with factory() as db:
            account = (
                await db.execute(
                    select(PlatformAdminAccount).where(
                        PlatformAdminAccount.status != "removed",
                        or_(
                            func.lower(PlatformAdminAccount.username) == value,
                            func.lower(PlatformAdminAccount.email) == value,
                        ),
                    )
                )
            ).scalars().first()
            stored = account.password_hash if account is not None and account.password_hash else _DUMMY_HASH
            ok = await asyncio.to_thread(verify_portal_password, stored, password)
            if account is None:
                return None
            if not ok or account.status != "active" or not account.password_hash:
                await record_admin_action(
                    actor=account.username,
                    action="platform_admin.sign_in_failed",
                    resource_type=RESOURCE_TYPE,
                    resource_id=str(account.id),
                    payload={"status": account.status, "ip": ip},
                    request=request,
                )
                return None
            account.last_sign_in_at = _utcnow()
            account.last_sign_in_ip = (ip or "")[:64] or None
            await db.commit()
    except Exception as exc:
        logger.warning("Stored admin sign-in unavailable: %s", exc)
        return None
    await refresh(force=True)
    return account


# --------------------------------------------------------------------------- console admins


async def console_platform_admins() -> list[dict[str, Any]]:
    """Read-only view of SAAS_PLATFORM_ADMIN_EMAILS (business-console platform admins)."""
    from server.services.saas.platform_admins import platform_admin_emails

    emails = sorted(platform_admin_emails())
    out: list[dict[str, Any]] = []
    factory = get_session_factory()
    users: dict[str, Any] = {}
    if factory is not None and emails:
        try:
            from server.db.models.saas_models import User

            async with factory() as db:
                rows = (
                    await db.execute(select(User).where(func.lower(User.email).in_(emails)))
                ).scalars().all()
            users = {r.email.lower(): r for r in rows}
        except Exception:
            users = {}
    for email in emails:
        user = users.get(email)
        out.append(
            {
                "email": email,
                "exists": user is not None,
                "fullName": getattr(user, "full_name", "") or "",
                "status": getattr(user, "status", None),
                "verified": bool(getattr(user, "email_verified_at", None)),
            }
        )
    return out
