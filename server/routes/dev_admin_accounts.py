"""Platform admin "Accounts" — one place for workspaces, users and phone numbers.

What this module adds on top of ``dev_admin``:

* Server-side filtered, sorted, paginated lists for the three views, each able to
  return every matching id (``idsOnly=true``) so the UI can "select all matching".
* Bulk endpoints for workspaces, users and numbers.

Bulk actions never re-implement a mutation. Each item is handed to the existing
single-item admin handler (``patch_tenant``, ``delete_tenant``, ``patch_number``,
``allocate_number``, ``release_number``, ...), so carrier rules (Vobiz customer-owned
numbers, KYC gate, release cool-off), validation and per-item audit entries stay
exactly where they were. This module adds only: permission checks, typed
confirmation for destructive actions, a written reason, per-item idempotency
(items already in the target state are reported as ``skipped``), a summary audit
entry, and an idempotency key so a double-submitted request is not replayed.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, asc, case, cast, delete, desc, exists, func, or_, select

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    AuthEvent,
    BillingWallet,
    NumberPurchase,
    TenantMembership,
    User,
    VobizSubaccount,
)
from server.routes import dev_admin as legacy
from server.services.saas.admin_audit import record_admin_action

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dev-admin-accounts"])

INVENTORY_TENANT_NAME = "Platform inventory"  # mirrors number_inventory.INVENTORY_TENANT_NAME
MAX_PAGE = 200
MAX_IDS = 5000
MAX_BULK = 500
MIN_REASON = 8

USER_ROLES = frozenset({"customer_admin", "customer_viewer", "voice_engineer", "platform_admin"})


def _require_db() -> None:
    if get_session_factory() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")


# --------------------------------------------------------------------------- helpers


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _uuid_or_none(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(_clean(raw))
    except (ValueError, AttributeError):
        return None


def _parse_day(raw: str, *, end: bool = False) -> datetime | None:
    raw = _clean(raw)
    if not raw:
        return None
    try:
        d = date.fromisoformat(raw[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date '{raw}'. Use YYYY-MM-DD.")
    t = dtime.max if end else dtime.min
    return datetime.combine(d, t, tzinfo=timezone.utc)


def _dial_code(raw: str) -> str:
    """Normalise a country dial code filter ("91", "+91") to digits only."""
    digits = "".join(ch for ch in _clean(raw) if ch.isdigit())
    if len(digits) > 4:
        raise HTTPException(status_code=400, detail="Invalid country dial code")
    return digits


def _order(column: Any, direction: str):
    return asc(column).nulls_last() if direction == "asc" else desc(column).nulls_last()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def is_inventory_condition():
    return and_(Tenant.name == INVENTORY_TENANT_NAME, Tenant.plan == "platform")


def kyc_state(status: str | None, blocked: bool | None, enabled: bool | None) -> str:
    """Collapse Vobiz sub-account KYC columns into one label (same rules as voice_kyc_service)."""
    if not status:
        return "not_started"
    blocked = True if blocked is None else bool(blocked)
    if status == "verified" and not blocked and bool(enabled):
        return "approved"
    if status in ("pending", "link_ready") or (status == "verified" and blocked):
        return "in_review"
    if status in ("failed", "revoked", "expired"):
        return "declined"
    return "not_started"


def _kyc_condition(value: str):
    sub = VobizSubaccount
    if value == "approved":
        return and_(sub.kyc_status == "verified", sub.kyc_calls_blocked.is_(False), sub.account_enabled.is_(True))
    if value == "in_review":
        return or_(sub.kyc_status.in_(("pending", "link_ready")), and_(sub.kyc_status == "verified", sub.kyc_calls_blocked.is_(True)))
    if value == "declined":
        return sub.kyc_status.in_(("failed", "revoked", "expired"))
    if value == "not_started":
        return or_(sub.tenant_id.is_(None), sub.kyc_status == "not_started")
    raise HTTPException(status_code=400, detail="kyc must be approved | in_review | declined | not_started")


def number_provider(pn: Any) -> str:
    """Same carrier attribution the existing admin number views use."""
    telnyx_id = getattr(pn, "telnyx_number_id", None)
    prov = "telnyx" if telnyx_id and telnyx_id != "carrier_platform" else "vobiz"
    if getattr(pn, "carrier_number_id", None) or str(getattr(pn, "e164", "")).startswith("+91"):
        prov = "vobiz"
    return prov


def _provider_condition(value: str):
    telnyx = and_(
        PhoneNumber.telnyx_number_id.is_not(None),
        PhoneNumber.telnyx_number_id != "carrier_platform",
        PhoneNumber.carrier_number_id.is_(None),
        ~PhoneNumber.e164.like("+91%"),
    )
    if value == "telnyx":
        return telnyx
    if value == "vobiz":
        return ~telnyx
    raise HTTPException(status_code=400, detail="provider must be vobiz | telnyx")


async def _fx_rate() -> float:
    try:
        from server.services.saas.billing_rates import load_current_rates

        return float((await load_current_rates())["fx_rate_inr"]) or 95.0
    except Exception:  # pragma: no cover - rates table missing in some envs
        return 95.0


def _wallet_usd(wallet: BillingWallet | None, fx: float) -> float:
    """Matches dev_admin.list_tenants: USD cents if any, else INR converted."""
    if wallet is None:
        return 0.0
    cents = int(wallet.balance_cents or 0)
    if cents:
        return round(cents / 100.0, 2)
    paise = int(wallet.balance_inr_paise or 0)
    return round((paise / 100.0) / fx, 2) if paise else 0.0


# --------------------------------------------------------------------------- summary


@router.get("/api/dev/admin/accounts/summary")
async def accounts_summary(session: SessionData = Depends(require_dev_session)):
    """Headline counts for the Accounts page. Read-only; creates nothing."""
    require_permission(session, "dev.admin.tenants")
    _require_db()
    async with get_session_factory()() as db:
        ws_rows = (
            await db.execute(
                select(Tenant.status, Tenant.deleted_at.is_(None), func.count())
                .where(~is_inventory_condition())
                .group_by(Tenant.status, Tenant.deleted_at.is_(None))
            )
        ).all()
        user_rows = (
            await db.execute(
                select(User.status, func.count()).where(User.deleted_at.is_(None)).group_by(User.status)
            )
        ).all()
        num_rows = (
            await db.execute(
                select(Tenant.name, Tenant.plan, PhoneNumber.status, PhoneNumber.agent_id.is_(None), func.count())
                .select_from(PhoneNumber)
                .outerjoin(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
                .where(PhoneNumber.released_at.is_(None))
                .group_by(Tenant.name, Tenant.plan, PhoneNumber.status, PhoneNumber.agent_id.is_(None))
            )
        ).all()
        kyc_blocked = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(VobizSubaccount)
                    .join(Tenant, Tenant.tenant_id == VobizSubaccount.tenant_id)
                    .where(Tenant.deleted_at.is_(None), VobizSubaccount.kyc_calls_blocked.is_(True))
                )
            ).scalar_one()
            or 0
        )

    workspaces: dict[str, int] = {"total": 0, "deleted": 0}
    for status, live, count in ws_rows:
        if not live:
            workspaces["deleted"] += int(count)
            continue
        workspaces["total"] += int(count)
        workspaces[status or "active"] = workspaces.get(status or "active", 0) + int(count)
    users: dict[str, int] = {"total": 0}
    for status, count in user_rows:
        users["total"] += int(count)
        users[status or "active"] = users.get(status or "active", 0) + int(count)
    numbers = {"total": 0, "assigned": 0, "inventory": 0, "releasePending": 0, "unpinned": 0}
    for t_name, t_plan, status, unpinned, count in num_rows:
        n = int(count)
        in_inventory = t_name == INVENTORY_TENANT_NAME and t_plan == "platform"
        numbers["total"] += n
        if status == "release_pending":
            numbers["releasePending"] += n
        if in_inventory:
            numbers["inventory"] += n
        else:
            numbers["assigned"] += n
            if unpinned:
                numbers["unpinned"] += n
    return {"workspaces": workspaces, "users": users, "numbers": numbers, "kycBlocked": kyc_blocked}


# --------------------------------------------------------------------------- workspaces list

_WS_SORTS = {"name", "created", "status", "plan", "numbers", "members", "agents", "balance"}


def build_workspaces_query(
    *,
    q: str = "",
    status: str = "",
    plan: str = "",
    kyc: str = "",
    has_numbers: str = "",
    dial_code: str = "",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    include_deleted: bool = False,
    include_inventory: bool = False,
    min_balance_usd: float | None = None,
    max_balance_usd: float | None = None,
    sort: str = "created",
    direction: str = "desc",
    fx: float = 95.0,
):
    """Return (row select, count select, id select) for the workspace list. Pure: no I/O."""
    num_sq = (
        select(PhoneNumber.tenant_id.label("tid"), func.count().label("n"))
        .where(PhoneNumber.released_at.is_(None))
        .group_by(PhoneNumber.tenant_id)
        .subquery("num_counts")
    )
    mem_sq = (
        select(TenantMembership.tenant_id.label("tid"), func.count().label("n"))
        .group_by(TenantMembership.tenant_id)
        .subquery("member_counts")
    )
    agent_sq = (
        select(Agent.tenant_id.label("tid"), func.count().label("n")).group_by(Agent.tenant_id).subquery("agent_counts")
    )
    n_numbers = func.coalesce(num_sq.c.n, 0)
    n_members = func.coalesce(mem_sq.c.n, 0)
    n_agents = func.coalesce(agent_sq.c.n, 0)
    balance = case(
        (func.coalesce(BillingWallet.balance_cents, 0) != 0, func.coalesce(BillingWallet.balance_cents, 0) / 100.0),
        else_=func.coalesce(BillingWallet.balance_inr_paise, 0) / 100.0 / fx,
    )

    def _joined(stmt):
        return (
            stmt.select_from(Tenant)
            .outerjoin(num_sq, num_sq.c.tid == Tenant.tenant_id)
            .outerjoin(mem_sq, mem_sq.c.tid == Tenant.tenant_id)
            .outerjoin(agent_sq, agent_sq.c.tid == Tenant.tenant_id)
            .outerjoin(BillingWallet, BillingWallet.tenant_id == Tenant.tenant_id)
            .outerjoin(VobizSubaccount, VobizSubaccount.tenant_id == Tenant.tenant_id)
        )

    conds: list[Any] = []
    status = _clean(status)
    if status == "deleted":
        conds.append(or_(Tenant.deleted_at.is_not(None), Tenant.status == "deleted"))
    else:
        if not include_deleted:
            conds.append(Tenant.deleted_at.is_(None))
        if status:
            conds.append(Tenant.status == status)
    if not include_inventory:
        conds.append(~is_inventory_condition())
    if _clean(q):
        pattern = f"%{_clean(q)}%"
        conds.append(or_(Tenant.name.ilike(pattern), cast(Tenant.tenant_id, String).ilike(pattern)))
    if _clean(plan):
        conds.append(Tenant.plan == _clean(plan))
    if _clean(kyc):
        conds.append(_kyc_condition(_clean(kyc)))
    if has_numbers in ("true", "yes"):
        conds.append(n_numbers > 0)
    elif has_numbers in ("false", "no"):
        conds.append(n_numbers == 0)
    if dial_code:
        conds.append(
            exists(
                select(PhoneNumber.id).where(
                    PhoneNumber.tenant_id == Tenant.tenant_id,
                    PhoneNumber.released_at.is_(None),
                    PhoneNumber.e164.like(f"+{dial_code}%"),
                )
            )
        )
    if created_from:
        conds.append(Tenant.created_at >= created_from)
    if created_to:
        conds.append(Tenant.created_at <= created_to)
    if min_balance_usd is not None:
        conds.append(balance >= min_balance_usd)
    if max_balance_usd is not None:
        conds.append(balance <= max_balance_usd)

    sort_cols = {
        "name": func.lower(Tenant.name),
        "created": Tenant.created_at,
        "status": Tenant.status,
        "plan": Tenant.plan,
        "numbers": n_numbers,
        "members": n_members,
        "agents": n_agents,
        "balance": balance,
    }
    if sort not in _WS_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {', '.join(sorted(_WS_SORTS))}")
    direction = "asc" if direction == "asc" else "desc"

    rows = _joined(
        select(
            Tenant,
            BillingWallet,
            VobizSubaccount.kyc_status,
            VobizSubaccount.kyc_calls_blocked,
            VobizSubaccount.account_enabled,
            n_numbers.label("n_numbers"),
            n_members.label("n_members"),
            n_agents.label("n_agents"),
        )
    ).where(*conds).order_by(_order(sort_cols[sort], direction), desc(Tenant.tenant_id))
    count = _joined(select(func.count(Tenant.tenant_id))).where(*conds)
    ids = _joined(select(Tenant.tenant_id)).where(*conds).order_by(_order(sort_cols[sort], direction), desc(Tenant.tenant_id))
    return rows, count, ids


@router.get("/api/dev/admin/accounts/workspaces")
async def list_workspaces(
    q: str = "",
    status: str = "",
    plan: str = "",
    kyc: str = "",
    hasNumbers: str = "",
    dialCode: str = "",
    createdFrom: str = "",
    createdTo: str = "",
    includeDeleted: bool = False,
    includeInventory: bool = False,
    minBalanceUsd: Optional[float] = None,
    maxBalanceUsd: Optional[float] = None,
    sort: str = "created",
    dir: str = "desc",
    limit: int = Query(25, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    idsOnly: bool = False,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    fx = await _fx_rate()
    rows_q, count_q, ids_q = build_workspaces_query(
        q=q,
        status=status,
        plan=plan,
        kyc=kyc,
        has_numbers=_clean(hasNumbers).lower(),
        dial_code=_dial_code(dialCode),
        created_from=_parse_day(createdFrom),
        created_to=_parse_day(createdTo, end=True),
        include_deleted=includeDeleted,
        include_inventory=includeInventory,
        min_balance_usd=minBalanceUsd,
        max_balance_usd=maxBalanceUsd,
        sort=_clean(sort) or "created",
        direction=_clean(dir),
        fx=fx,
    )
    async with get_session_factory()() as db:
        total = int((await db.execute(count_q)).scalar_one() or 0)
        if idsOnly:
            ids = (await db.execute(ids_q.limit(MAX_IDS))).scalars().all()
            return {"ids": [str(i) for i in ids], "total": total, "truncated": total > MAX_IDS}
        rows = (await db.execute(rows_q.limit(limit).offset(offset))).all()
    items = []
    for tenant, wallet, kyc_status, kyc_blocked, account_enabled, n_numbers, n_members, n_agents in rows:
        items.append(
            {
                "tenantId": str(tenant.tenant_id),
                "name": tenant.name,
                "status": "deleted" if tenant.deleted_at is not None and tenant.status != "deleted" else tenant.status,
                "plan": tenant.plan,
                "billingSource": tenant.billing_source,
                "createdAt": _iso(tenant.created_at),
                "deletedAt": _iso(tenant.deleted_at),
                "scheduledPurgeAt": _iso(getattr(tenant, "scheduled_purge_at", None)),
                "walletBalanceUsd": _wallet_usd(wallet, fx),
                "walletBalanceInr": round(int(getattr(wallet, "balance_inr_paise", 0) or 0) / 100.0, 2),
                "walletCurrency": ((getattr(wallet, "currency", None) or "usd")).upper(),
                "numberCount": int(n_numbers or 0),
                "memberCount": int(n_members or 0),
                "agentCount": int(n_agents or 0),
                "kyc": kyc_state(kyc_status, kyc_blocked, account_enabled),
                "kycStatus": kyc_status,
                "callsBlocked": bool(kyc_blocked) if kyc_status else None,
                "isInventory": tenant.name == INVENTORY_TENANT_NAME and tenant.plan == "platform",
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset, "fxRateInr": fx}


@router.get("/api/dev/admin/accounts/workspaces/{tenant_id}/agents")
async def workspace_agents(tenant_id: str, session: SessionData = Depends(require_dev_session)):
    """Agents in one workspace, for the 'pin number to agent' picker."""
    require_permission(session, "dev.admin.numbers")
    _require_db()
    tid = _uuid_or_none(tenant_id)
    if tid is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    async with get_session_factory()() as db:
        pinned = (
            select(PhoneNumber.agent_id.label("aid"), func.count().label("n"))
            .where(PhoneNumber.released_at.is_(None), PhoneNumber.agent_id.is_not(None))
            .group_by(PhoneNumber.agent_id)
            .subquery()
        )
        rows = (
            await db.execute(
                select(Agent, func.coalesce(pinned.c.n, 0))
                .outerjoin(pinned, pinned.c.aid == Agent.agent_id)
                .where(Agent.tenant_id == tid)
                .order_by(func.lower(Agent.name))
            )
        ).all()
    return {
        "agents": [
            {"agentId": str(a.agent_id), "name": a.name, "status": a.status, "numberCount": int(n or 0)}
            for a, n in rows
        ]
    }


# --------------------------------------------------------------------------- users list

_USER_SORTS = {"email", "name", "created", "lastLogin", "status"}
_LAST_ACTIVE = {"7d", "30d", "90d", "inactive30", "inactive90", "never"}


def build_users_query(
    *,
    q: str = "",
    status: str = "",
    role: str = "",
    tenant_id: uuid.UUID | None = None,
    no_workspace: bool = False,
    last_active: str = "",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    include_deleted: bool = False,
    sort: str = "created",
    direction: str = "desc",
    now: datetime | None = None,
):
    now = now or datetime.now(timezone.utc)
    login_sq = (
        select(AuthEvent.user_id.label("uid"), func.max(AuthEvent.created_at).label("last_login"))
        .where(AuthEvent.event_type == "login")
        .group_by(AuthEvent.user_id)
        .subquery("last_logins")
    )
    mem_sq = (
        select(TenantMembership.user_id.label("uid"), func.count().label("n"))
        .group_by(TenantMembership.user_id)
        .subquery("membership_counts")
    )

    def _joined(stmt):
        return stmt.select_from(User).outerjoin(login_sq, login_sq.c.uid == User.user_id).outerjoin(
            mem_sq, mem_sq.c.uid == User.user_id
        )

    conds: list[Any] = []
    if not include_deleted:
        conds.append(User.deleted_at.is_(None))
    if _clean(q):
        pattern = f"%{_clean(q)}%"
        conds.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern), cast(User.user_id, String).ilike(pattern)))
    status = _clean(status)
    if status == "invited":
        conds.append(User.status.in_(("invited", "pending_invite")))
    elif status:
        conds.append(User.status == status)
    if tenant_id is not None:
        member = select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id)
        if _clean(role):
            member = member.where(TenantMembership.role == _clean(role))
        conds.append(User.user_id.in_(member))
    elif _clean(role):
        conds.append(User.user_id.in_(select(TenantMembership.user_id).where(TenantMembership.role == _clean(role))))
    if no_workspace:
        conds.append(func.coalesce(mem_sq.c.n, 0) == 0)
    last_active = _clean(last_active)
    if last_active:
        if last_active not in _LAST_ACTIVE:
            raise HTTPException(status_code=400, detail=f"lastActive must be one of {', '.join(sorted(_LAST_ACTIVE))}")
        if last_active == "never":
            conds.append(login_sq.c.last_login.is_(None))
        elif last_active.startswith("inactive"):
            days = int(last_active.removeprefix("inactive"))
            conds.append(or_(login_sq.c.last_login.is_(None), login_sq.c.last_login < now - timedelta(days=days)))
        else:
            days = int(last_active.removesuffix("d"))
            conds.append(login_sq.c.last_login >= now - timedelta(days=days))
    if created_from:
        conds.append(User.created_at >= created_from)
    if created_to:
        conds.append(User.created_at <= created_to)

    sort_cols = {
        "email": func.lower(User.email),
        "name": func.lower(User.full_name),
        "created": User.created_at,
        "lastLogin": login_sq.c.last_login,
        "status": User.status,
    }
    if sort not in _USER_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {', '.join(sorted(_USER_SORTS))}")
    direction = "asc" if direction == "asc" else "desc"
    order = (_order(sort_cols[sort], direction), desc(User.user_id))
    rows = _joined(select(User, login_sq.c.last_login, func.coalesce(mem_sq.c.n, 0))).where(*conds).order_by(*order)
    count = _joined(select(func.count(User.user_id))).where(*conds)
    ids = _joined(select(User.user_id)).where(*conds).order_by(*order)
    return rows, count, ids


@router.get("/api/dev/admin/accounts/users")
async def list_account_users(
    q: str = "",
    status: str = "",
    role: str = "",
    tenantId: str = "",
    noWorkspace: bool = False,
    lastActive: str = "",
    createdFrom: str = "",
    createdTo: str = "",
    includeDeleted: bool = False,
    sort: str = "created",
    dir: str = "desc",
    limit: int = Query(25, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    idsOnly: bool = False,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.users")
    _require_db()
    tid = None
    if _clean(tenantId):
        tid = _uuid_or_none(tenantId)
        if tid is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset} if not idsOnly else {"ids": [], "total": 0, "truncated": False}
    rows_q, count_q, ids_q = build_users_query(
        q=q,
        status=status,
        role=role,
        tenant_id=tid,
        no_workspace=noWorkspace,
        last_active=lastActive,
        created_from=_parse_day(createdFrom),
        created_to=_parse_day(createdTo, end=True),
        include_deleted=includeDeleted,
        sort=_clean(sort) or "created",
        direction=_clean(dir),
    )
    async with get_session_factory()() as db:
        total = int((await db.execute(count_q)).scalar_one() or 0)
        if idsOnly:
            ids = (await db.execute(ids_q.limit(MAX_IDS))).scalars().all()
            return {"ids": [str(i) for i in ids], "total": total, "truncated": total > MAX_IDS}
        rows = (await db.execute(rows_q.limit(limit).offset(offset))).all()
        user_ids = [u.user_id for u, _ll, _n in rows]
        memberships: dict[uuid.UUID, list[dict[str, Any]]] = {}
        if user_ids:
            mem_rows = (
                await db.execute(
                    select(TenantMembership, Tenant.name, Tenant.status)
                    .outerjoin(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
                    .where(TenantMembership.user_id.in_(user_ids))
                    .order_by(TenantMembership.created_at)
                )
            ).all()
            for m, t_name, t_status in mem_rows:
                memberships.setdefault(m.user_id, []).append(
                    {"tenantId": str(m.tenant_id), "tenantName": t_name or str(m.tenant_id), "tenantStatus": t_status, "role": m.role}
                )
    items = []
    for u, last_login, _n in rows:
        mems = memberships.get(u.user_id, [])
        focus = next((m for m in mems if tid and m["tenantId"] == str(tid)), mems[0] if mems else None)
        items.append(
            {
                "userId": str(u.user_id),
                "email": u.email,
                "fullName": u.full_name or "",
                "status": u.status,
                "emailVerified": bool(u.email_verified_at),
                "createdAt": _iso(u.created_at),
                "deletedAt": _iso(u.deleted_at),
                "lastLoginAt": _iso(last_login),
                "role": focus["role"] if focus else None,
                "tenantId": focus["tenantId"] if focus else None,
                "tenantName": focus["tenantName"] if focus else None,
                "memberships": mems,
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# --------------------------------------------------------------------------- numbers list

_NUM_SORTS = {"e164", "created", "workspace", "status", "agent"}


def build_numbers_query(
    *,
    q: str = "",
    tenant_id: uuid.UUID | None = None,
    location: str = "",
    status: str = "",
    provider: str = "",
    ownership: str = "",
    pinned: str = "",
    dial_code: str = "",
    purchase_status: str = "",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "created",
    direction: str = "desc",
):
    def _joined(stmt):
        return (
            stmt.select_from(PhoneNumber)
            .outerjoin(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
            .outerjoin(Agent, Agent.agent_id == PhoneNumber.agent_id)
            .outerjoin(NumberPurchase, NumberPurchase.id == PhoneNumber.purchase_id)
        )

    conds: list[Any] = [PhoneNumber.released_at.is_(None)]
    if _clean(q):
        pattern = f"%{_clean(q)}%"
        conds.append(
            or_(
                PhoneNumber.e164.ilike(pattern),
                Tenant.name.ilike(pattern),
                Agent.name.ilike(pattern),
                PhoneNumber.carrier_number_id.ilike(pattern),
                PhoneNumber.telnyx_number_id.ilike(pattern),
                cast(PhoneNumber.id, String).ilike(pattern),
            )
        )
    if tenant_id is not None:
        conds.append(PhoneNumber.tenant_id == tenant_id)
    location = _clean(location)
    if location == "inventory":
        conds.append(is_inventory_condition())
    elif location == "assigned":
        conds.append(~is_inventory_condition())
    elif location:
        raise HTTPException(status_code=400, detail="location must be assigned | inventory")
    if _clean(status):
        conds.append(PhoneNumber.status == _clean(status))
    if _clean(provider):
        conds.append(_provider_condition(_clean(provider)))
    ownership = _clean(ownership)
    if ownership == "customer":
        conds.append(PhoneNumber.vobiz_account_scope == "tenant")
    elif ownership == "platform":
        conds.append(or_(PhoneNumber.vobiz_account_scope.is_(None), PhoneNumber.vobiz_account_scope != "tenant"))
    elif ownership:
        raise HTTPException(status_code=400, detail="ownership must be customer | platform")
    if pinned in ("true", "yes"):
        conds.append(PhoneNumber.agent_id.is_not(None))
    elif pinned in ("false", "no"):
        conds.append(PhoneNumber.agent_id.is_(None))
    if dial_code:
        conds.append(PhoneNumber.e164.like(f"+{dial_code}%"))
    purchase_status = _clean(purchase_status)
    if purchase_status == "manual":
        conds.append(PhoneNumber.purchase_id.is_(None))
    elif purchase_status:
        conds.append(NumberPurchase.status == purchase_status)
    if created_from:
        conds.append(PhoneNumber.created_at >= created_from)
    if created_to:
        conds.append(PhoneNumber.created_at <= created_to)

    sort_cols = {
        "e164": PhoneNumber.e164,
        "created": PhoneNumber.created_at,
        "workspace": func.lower(Tenant.name),
        "status": PhoneNumber.status,
        "agent": func.lower(Agent.name),
    }
    if sort not in _NUM_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {', '.join(sorted(_NUM_SORTS))}")
    direction = "asc" if direction == "asc" else "desc"
    order = (_order(sort_cols[sort], direction), desc(PhoneNumber.id))
    rows = _joined(select(PhoneNumber, Tenant, Agent.name, NumberPurchase.status)).where(*conds).order_by(*order)
    count = _joined(select(func.count(PhoneNumber.id))).where(*conds)
    ids = _joined(select(PhoneNumber.id)).where(*conds).order_by(*order)
    return rows, count, ids


@router.get("/api/dev/admin/accounts/numbers")
async def list_account_numbers(
    q: str = "",
    tenantId: str = "",
    location: str = "",
    status: str = "",
    provider: str = "",
    ownership: str = "",
    pinned: str = "",
    dialCode: str = "",
    purchaseStatus: str = "",
    createdFrom: str = "",
    createdTo: str = "",
    sort: str = "created",
    dir: str = "desc",
    limit: int = Query(25, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    idsOnly: bool = False,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    tid = None
    if _clean(tenantId):
        tid = _uuid_or_none(tenantId)
        if tid is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset} if not idsOnly else {"ids": [], "total": 0, "truncated": False}
    rows_q, count_q, ids_q = build_numbers_query(
        q=q,
        tenant_id=tid,
        location=location,
        status=status,
        provider=provider,
        ownership=ownership,
        pinned=_clean(pinned).lower(),
        dial_code=_dial_code(dialCode),
        purchase_status=purchaseStatus,
        created_from=_parse_day(createdFrom),
        created_to=_parse_day(createdTo, end=True),
        sort=_clean(sort) or "created",
        direction=_clean(dir),
    )
    from server.services.telephony import active_telephony_provider

    try:
        active = active_telephony_provider()
    except Exception:  # pragma: no cover
        active = None
    async with get_session_factory()() as db:
        total = int((await db.execute(count_q)).scalar_one() or 0)
        if idsOnly:
            ids = (await db.execute(ids_q.limit(MAX_IDS))).scalars().all()
            return {"ids": [str(i) for i in ids], "total": total, "truncated": total > MAX_IDS}
        rows = (await db.execute(rows_q.limit(limit).offset(offset))).all()
    items = []
    for pn, tenant, agent_name, purchase_status in rows:
        in_inventory = bool(tenant is not None and tenant.name == INVENTORY_TENANT_NAME and tenant.plan == "platform")
        items.append(
            {
                "numberId": str(pn.id),
                "e164": pn.e164,
                "status": pn.status,
                "provider": number_provider(pn),
                "customerOwned": pn.vobiz_account_scope == "tenant",
                "inInventory": in_inventory,
                "tenantId": None if in_inventory else (str(pn.tenant_id) if pn.tenant_id else None),
                "tenantName": INVENTORY_TENANT_NAME if in_inventory else (tenant.name if tenant else None),
                "tenantStatus": None if in_inventory or tenant is None else ("deleted" if tenant.deleted_at else tenant.status),
                "agentId": str(pn.agent_id) if pn.agent_id else None,
                "agentName": agent_name,
                "purchaseStatus": purchase_status,
                "billingSource": pn.billing_source,
                "carrierNumberId": pn.carrier_number_id,
                "telnyxNumberId": pn.telnyx_number_id,
                "inboundEnabled": bool(pn.inbound_enabled),
                "outboundEnabled": bool(pn.outbound_enabled),
                "createdAt": _iso(pn.created_at),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset, "activeProvider": active}


# --------------------------------------------------------------------------- bulk plumbing


class BulkBody(BaseModel):
    action: str = Field(..., min_length=1, max_length=40)
    ids: list[str] = Field(..., min_length=1, max_length=MAX_BULK)
    reason: str = Field("", max_length=500)
    confirm: str = Field("", max_length=64)
    idempotencyKey: Optional[str] = Field(None, max_length=80)
    # workspace options
    plan: Optional[str] = None
    releaseNumbers: bool = False
    revokeSessions: bool = True
    force: bool = False
    # user options
    tenantId: Optional[str] = None
    role: Optional[str] = None
    # number options
    agentId: Optional[str] = None


_IDEMPOTENCY: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_IDEMPOTENCY_TTL = 15 * 60


def _idempotent_get(actor: str, key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    now = time.monotonic()
    for k in [k for k, (exp, _r) in _IDEMPOTENCY.items() if exp < now]:
        _IDEMPOTENCY.pop(k, None)
    hit = _IDEMPOTENCY.get((actor, key))
    return {**hit[1], "replayed": True} if hit else None


def _idempotent_put(actor: str, key: str | None, result: dict[str, Any]) -> None:
    if key:
        _IDEMPOTENCY[(actor, key)] = (time.monotonic() + _IDEMPOTENCY_TTL, result)


def confirm_phrase(action: str, count: int) -> str:
    """The text an operator must type for a destructive bulk action."""
    return f"{action.upper().replace('_', ' ')} {count}"


def _check_reason_and_confirm(body: BulkBody, action: str, destructive: frozenset[str]) -> None:
    if len(body.reason.strip()) < MIN_REASON:
        raise HTTPException(status_code=400, detail=f"A reason of at least {MIN_REASON} characters is required.")
    if action in destructive:
        expected = confirm_phrase(action, len(set(body.ids)))
        if body.confirm.strip().upper() != expected:
            raise HTTPException(status_code=400, detail=f"Type '{expected}' to confirm this action.")


def _error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        d = exc.detail
        if isinstance(d, dict):
            return str((d.get("error") or {}).get("message") or d)
        return str(d)
    return str(exc) or exc.__class__.__name__


class _Results:
    def __init__(self) -> None:
        self.processed: list[str] = []
        self.skipped: list[dict[str, str]] = []
        self.failed: list[dict[str, str]] = []

    def payload(self, action: str) -> dict[str, Any]:
        return {
            "ok": not self.failed,
            "action": action,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "counts": {"processed": len(self.processed), "skipped": len(self.skipped), "failed": len(self.failed)},
        }


async def _audit_bulk(session: SessionData, kind: str, action: str, body: BulkBody, results: _Results, extra: dict | None = None):
    await record_admin_action(
        actor=session.subject,
        action=f"{kind}.bulk.{action}",
        resource_type=kind,
        resource_id=f"bulk:{len(body.ids)}",
        payload={
            "reason": body.reason.strip(),
            "requested": len(body.ids),
            "processed": results.processed[:MAX_BULK],
            "skipped": len(results.skipped),
            "failed": results.failed[:50],
            **(extra or {}),
        },
    )


def _dedupe(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for raw in ids:
        if raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


# --------------------------------------------------------------------------- workspaces bulk

WS_ACTIONS = frozenset({"suspend", "activate", "change_plan", "delete", "restore"})
WS_DESTRUCTIVE = frozenset({"suspend", "delete"})


async def _load_tenants(ids: list[uuid.UUID]) -> dict[uuid.UUID, Tenant]:
    async with get_session_factory()() as db:
        rows = (await db.execute(select(Tenant).where(Tenant.tenant_id.in_(ids)))).scalars().all()
    return {t.tenant_id: t for t in rows}


@router.post("/api/dev/admin/accounts/workspaces/bulk")
async def bulk_workspaces(body: BulkBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.tenants")
    _require_db()
    action = body.action.strip().lower()
    if action not in WS_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {', '.join(sorted(WS_ACTIONS))}")
    if action == "change_plan" and (body.plan or "") not in legacy._TENANT_PLAN_VALUES:
        raise HTTPException(status_code=400, detail="A valid plan is required for change_plan.")
    _check_reason_and_confirm(body, action, WS_DESTRUCTIVE)
    replay = _idempotent_get(session.subject, body.idempotencyKey)
    if replay:
        return replay

    reason = body.reason.strip()
    ids = _dedupe(body.ids)
    parsed = {raw: _uuid_or_none(raw) for raw in ids}
    tenants = await _load_tenants([t for t in parsed.values() if t])
    res = _Results()
    for raw, tid in parsed.items():
        tenant = tenants.get(tid) if tid else None
        if tenant is None:
            res.failed.append({"id": raw, "error": "Workspace not found"})
            continue
        if tenant.name == INVENTORY_TENANT_NAME and tenant.plan == "platform":
            res.failed.append({"id": raw, "error": "The platform inventory workspace cannot be changed in bulk"})
            continue
        deleted = tenant.deleted_at is not None or tenant.status == "deleted"
        try:
            if action == "suspend":
                if deleted:
                    res.skipped.append({"id": raw, "reason": "deleted"})
                    continue
                if tenant.status == "suspended":
                    res.skipped.append({"id": raw, "reason": "already suspended"})
                    continue
                await legacy.patch_tenant(
                    tenant_id=raw,
                    body=legacy.TenantPatchBody(
                        status="suspended", note=reason, releaseNumbers=body.releaseNumbers, revokeSessions=body.revokeSessions
                    ),
                    session=session,
                )
            elif action == "activate":
                if deleted:
                    await legacy.restore_tenant(tenant_id=raw, note=reason, session=session)
                elif tenant.status == "active":
                    res.skipped.append({"id": raw, "reason": "already active"})
                    continue
                else:
                    await legacy.patch_tenant(
                        tenant_id=raw, body=legacy.TenantPatchBody(status="active", note=reason), session=session
                    )
            elif action == "restore":
                if not deleted:
                    res.skipped.append({"id": raw, "reason": "not deleted"})
                    continue
                await legacy.restore_tenant(tenant_id=raw, note=reason, session=session)
            elif action == "change_plan":
                if deleted:
                    res.skipped.append({"id": raw, "reason": "deleted"})
                    continue
                if tenant.plan == body.plan:
                    res.skipped.append({"id": raw, "reason": f"already on {body.plan}"})
                    continue
                await legacy.patch_tenant(
                    tenant_id=raw, body=legacy.TenantPatchBody(plan=body.plan, note=reason), session=session
                )
            elif action == "delete":
                if deleted:
                    res.skipped.append({"id": raw, "reason": "already deleted"})
                    continue
                out = await legacy.delete_tenant(
                    tenant_id=raw,
                    force=body.force,
                    release_numbers=body.releaseNumbers,
                    revoke_sessions=body.revokeSessions,
                    hard=False,
                    note=reason,
                    body=None,
                    session=session,
                )
                if isinstance(out, dict) and out.get("alreadyDeleted"):
                    res.skipped.append({"id": raw, "reason": "already deleted"})
                    continue
            res.processed.append(raw)
        except Exception as exc:  # each item reports its own failure
            res.failed.append({"id": raw, "error": _error_text(exc)})

    result = res.payload(action)
    await _audit_bulk(
        session,
        "tenant",
        action,
        body,
        res,
        {"plan": body.plan, "releaseNumbers": body.releaseNumbers, "revokeSessions": body.revokeSessions, "force": body.force},
    )
    _idempotent_put(session.subject, body.idempotencyKey, result)
    return result


# --------------------------------------------------------------------------- users bulk

USER_ACTIONS = frozenset(
    {"suspend", "activate", "set_role", "add_to_workspace", "remove_from_workspace", "revoke_sessions", "delete"}
)
USER_DESTRUCTIVE = frozenset({"suspend", "delete", "remove_from_workspace"})


async def _load_users(ids: list[uuid.UUID], tenant_id: uuid.UUID | None):
    async with get_session_factory()() as db:
        users = (await db.execute(select(User).where(User.user_id.in_(ids)))).scalars().all()
        mems: dict[uuid.UUID, TenantMembership] = {}
        admin_count = 0
        tenant = None
        if tenant_id is not None:
            tenant = await db.get(Tenant, tenant_id)
            for m in (
                await db.execute(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id))
            ).scalars().all():
                if m.role == "customer_admin":
                    admin_count += 1
                if m.user_id in ids:
                    mems[m.user_id] = m
    return {u.user_id: u for u in users}, mems, admin_count, tenant


async def _set_membership_role(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str | None:
    async with get_session_factory()() as db:
        m = (
            await db.execute(
                select(TenantMembership).where(TenantMembership.user_id == user_id, TenantMembership.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if m is None:
            raise HTTPException(status_code=404, detail="Not a member of this workspace")
        previous = m.role
        m.role = role
        await db.commit()
    return previous


async def _remove_membership(user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    async with get_session_factory()() as db:
        await db.execute(
            delete(TenantMembership).where(TenantMembership.user_id == user_id, TenantMembership.tenant_id == tenant_id)
        )
        await db.commit()


@router.post("/api/dev/admin/accounts/users/bulk")
async def bulk_users(body: BulkBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.users")
    _require_db()
    action = body.action.strip().lower()
    if action not in USER_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {', '.join(sorted(USER_ACTIONS))}")
    tid = None
    if action in {"set_role", "add_to_workspace", "remove_from_workspace"}:
        tid = _uuid_or_none(body.tenantId or "")
        if tid is None:
            raise HTTPException(status_code=400, detail="Choose a workspace for this action.")
    if action in {"set_role", "add_to_workspace"} and (body.role or "") not in USER_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(sorted(USER_ROLES))}")
    _check_reason_and_confirm(body, action, USER_DESTRUCTIVE)
    replay = _idempotent_get(session.subject, body.idempotencyKey)
    if replay:
        return replay

    from server.services.saas import auth_service

    ids = _dedupe(body.ids)
    parsed = {raw: _uuid_or_none(raw) for raw in ids}
    users, mems, admin_count, tenant = await _load_users([u for u in parsed.values() if u], tid)
    if tid is not None and (tenant is None or tenant.deleted_at is not None):
        raise HTTPException(status_code=404, detail="Workspace not found")
    me = (session.subject or "").strip().lower()
    res = _Results()
    for raw, uid in parsed.items():
        user = users.get(uid) if uid else None
        if user is None or user.deleted_at is not None:
            res.failed.append({"id": raw, "error": "User not found"})
            continue
        is_self = (user.email or "").strip().lower() == me
        try:
            if action in {"suspend", "delete", "revoke_sessions"} and is_self:
                res.failed.append({"id": raw, "error": "You cannot apply this to your own account"})
                continue
            if action == "suspend":
                if user.status == "suspended":
                    res.skipped.append({"id": raw, "reason": "already suspended"})
                    continue
                await legacy.patch_user(user_id=raw, body=legacy.UserPatchBody(status="suspended"), session=session)
                if body.revokeSessions:
                    await auth_service.logout_all(uid)
            elif action == "activate":
                if user.status == "active":
                    res.skipped.append({"id": raw, "reason": "already active"})
                    continue
                await legacy.patch_user(user_id=raw, body=legacy.UserPatchBody(status="active"), session=session)
            elif action == "revoke_sessions":
                await auth_service.logout_all(uid)
                await record_admin_action(
                    actor=session.subject, action="user.revoke_sessions", resource_type="user", resource_id=raw,
                    payload={"reason": body.reason.strip()},
                )
            elif action == "delete":
                await legacy.admin_delete_user(user_id=raw, session=session)
            elif action == "add_to_workspace":
                if uid in mems:
                    res.skipped.append({"id": raw, "reason": "already a member"})
                    continue
                await legacy.admin_membership(
                    body=legacy.MembershipBody(userId=raw, tenantId=str(tid), role=body.role or "customer_viewer"),
                    session=session,
                )
                mems[uid] = TenantMembership(user_id=uid, tenant_id=tid, role=body.role)
                if body.role == "customer_admin":
                    admin_count += 1
            elif action == "set_role":
                current = mems.get(uid)
                if current is None:
                    res.failed.append({"id": raw, "error": "Not a member of this workspace"})
                    continue
                if current.role == body.role:
                    res.skipped.append({"id": raw, "reason": f"already {body.role}"})
                    continue
                if current.role == "customer_admin" and admin_count <= 1:
                    res.failed.append({"id": raw, "error": "This is the workspace's last admin; promote someone else first"})
                    continue
                previous = await _set_membership_role(uid, tid, body.role or "")
                if previous == "customer_admin":
                    admin_count -= 1
                if body.role == "customer_admin":
                    admin_count += 1
                current.role = body.role
                await record_admin_action(
                    actor=session.subject, action="membership.role_change", resource_type="membership",
                    resource_id=f"{raw}:{tid}", tenant_id=tid,
                    payload={"from": previous, "to": body.role, "reason": body.reason.strip()},
                )
            elif action == "remove_from_workspace":
                current = mems.get(uid)
                if current is None:
                    res.skipped.append({"id": raw, "reason": "not a member"})
                    continue
                if current.role == "customer_admin" and admin_count <= 1:
                    res.failed.append({"id": raw, "error": "This is the workspace's last admin; promote someone else first"})
                    continue
                await _remove_membership(uid, tid)
                if current.role == "customer_admin":
                    admin_count -= 1
                mems.pop(uid, None)
                await record_admin_action(
                    actor=session.subject, action="membership.delete", resource_type="membership",
                    resource_id=f"{raw}:{tid}", tenant_id=tid,
                    payload={"role": current.role, "reason": body.reason.strip()},
                )
            res.processed.append(raw)
        except Exception as exc:
            res.failed.append({"id": raw, "error": _error_text(exc)})

    result = res.payload(action)
    await _audit_bulk(session, "user", action, body, res, {"tenantId": str(tid) if tid else None, "role": body.role})
    _idempotent_put(session.subject, body.idempotencyKey, result)
    return result


# --------------------------------------------------------------------------- numbers bulk

NUMBER_ACTIONS = frozenset({"assign_workspace", "assign_agent", "unassign_agent", "release"})
NUMBER_DESTRUCTIVE = frozenset({"release"})


async def _load_numbers(ids: list[uuid.UUID]):
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(PhoneNumber, Tenant)
                .outerjoin(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
                .where(PhoneNumber.id.in_(ids))
            )
        ).all()
    return {pn.id: (pn, t) for pn, t in rows}


async def _load_agent(agent_id: uuid.UUID) -> Agent | None:
    async with get_session_factory()() as db:
        return await db.get(Agent, agent_id)


@router.post("/api/dev/admin/accounts/numbers/bulk")
async def bulk_numbers(body: BulkBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    action = body.action.strip().lower()
    if action not in NUMBER_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {', '.join(sorted(NUMBER_ACTIONS))}")
    target_tid = None
    target_tenant = None
    agent = None
    if action == "assign_workspace":
        target_tid = _uuid_or_none(body.tenantId or "")
        if target_tid is None:
            raise HTTPException(status_code=400, detail="Choose the workspace to assign to.")
        target_tenant = (await _load_tenants([target_tid])).get(target_tid)
        if target_tenant is None or target_tenant.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if target_tenant.name == INVENTORY_TENANT_NAME and target_tenant.plan == "platform":
            raise HTTPException(status_code=400, detail="Use 'Release to inventory' to return numbers to the pool.")
        if target_tenant.status != "active":
            raise HTTPException(status_code=409, detail=f"Workspace is {target_tenant.status}; activate it first.")
    if action == "assign_agent":
        aid = _uuid_or_none(body.agentId or "")
        agent = await _load_agent(aid) if aid else None
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
    _check_reason_and_confirm(body, action, NUMBER_DESTRUCTIVE)
    replay = _idempotent_get(session.subject, body.idempotencyKey)
    if replay:
        return replay

    ids = _dedupe(body.ids)
    parsed = {raw: _uuid_or_none(raw) for raw in ids}
    numbers = await _load_numbers([n for n in parsed.values() if n])
    res = _Results()
    for raw, nid in parsed.items():
        found = numbers.get(nid) if nid else None
        if found is None or found[0].released_at is not None:
            res.failed.append({"id": raw, "error": "Number not found"})
            continue
        pn, tenant = found
        in_inventory = bool(tenant is not None and tenant.name == INVENTORY_TENANT_NAME and tenant.plan == "platform")
        label = pn.e164
        try:
            if pn.status == "release_pending" and action != "release":
                res.failed.append({"id": raw, "error": f"{label} is being released by the carrier"})
                continue
            if action == "assign_workspace":
                if pn.tenant_id == target_tid:
                    res.skipped.append({"id": raw, "reason": "already in this workspace"})
                    continue
                if in_inventory:
                    # Same path as "Assign number to workspace": KYC gate, carrier
                    # ownership check, activation and wallet creation.
                    await legacy.allocate_number(
                        body=legacy.AllocateNumberBody(
                            e164=pn.e164, tenantId=str(target_tid), telnyxNumberId=pn.telnyx_number_id
                        ),
                        session=session,
                    )
                else:
                    # Moving between workspaces clears the agent pin: the old agent
                    # belongs to the old workspace. patch_number refuses customer-owned
                    # Vobiz numbers (they need carrier reconciliation).
                    await legacy.patch_number(
                        number_id=raw,
                        body=legacy.NumberPatchBody(tenantId=str(target_tid), agentId=""),
                        session=session,
                    )
            elif action == "assign_agent":
                if in_inventory:
                    res.failed.append({"id": raw, "error": f"{label} is in inventory; assign it to a workspace first"})
                    continue
                if pn.tenant_id != agent.tenant_id:
                    res.failed.append({"id": raw, "error": f"{label} belongs to a different workspace than the agent"})
                    continue
                if pn.agent_id == agent.agent_id:
                    res.skipped.append({"id": raw, "reason": "already pinned to this agent"})
                    continue
                await legacy.patch_number(
                    number_id=raw, body=legacy.NumberPatchBody(agentId=str(agent.agent_id)), session=session
                )
            elif action == "unassign_agent":
                if pn.agent_id is None:
                    res.skipped.append({"id": raw, "reason": "not pinned"})
                    continue
                await legacy.patch_number(number_id=raw, body=legacy.NumberPatchBody(agentId=""), session=session)
            elif action == "release":
                if in_inventory:
                    res.skipped.append({"id": raw, "reason": "already in inventory"})
                    continue
                if pn.status == "release_pending":
                    res.skipped.append({"id": raw, "reason": "release already pending"})
                    continue
                await legacy.release_number(
                    number_id=raw, session=session, body=legacy.ReleaseNumberBody(note=body.reason.strip())
                )
            res.processed.append(raw)
        except Exception as exc:
            res.failed.append({"id": raw, "error": f"{label}: {_error_text(exc)}"})

    result = res.payload(action)
    await _audit_bulk(
        session,
        "phone_number",
        action,
        body,
        res,
        {"tenantId": str(target_tid) if target_tid else None, "agentId": body.agentId},
    )
    _idempotent_put(session.subject, body.idempotencyKey, result)
    return result
