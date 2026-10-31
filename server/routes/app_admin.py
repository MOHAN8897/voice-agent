"""Subscriber platform-admin API — allowlist is re-checked from env every request."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import BillingWallet, NumberPurchase, User

logger = logging.getLogger(__name__)
from server.services.saas.admin_wallet_adjust import (
    IDEMPOTENCY_KEY_PATTERN,
    adjustment_already_posted,
    admin_adjust_kind,
    admin_adjust_reference,
    tenant_exists,
)
from server.services.saas.billing_wallet_service import credit_wallet, wallet_summary
from server.services.saas.platform_admins import require_platform_admin_email
from server.services.saas.tenant_guard import SubscriberPrincipal

router = APIRouter()


def _require_admin(principal: SubscriberPrincipal) -> None:
    require_platform_admin_email(principal.email)


class CreditBody(BaseModel):
    tenantId: str
    amountInrPaise: int = Field(..., ge=-50_000_000, le=50_000_000)
    # Recorded in the audit log only; the ledger kind is fixed by the sign.
    reason: str = Field("admin_grant", max_length=80)
    note: str = Field("", max_length=500)
    idempotencyKey: str | None = Field(None, pattern=IDEMPOTENCY_KEY_PATTERN)


@router.post("/api/admin/credits")
async def admin_credits(body: CreditBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Older console-token route; books exactly like /api/dev/admin/wallets/adjust."""
    _require_admin(principal)
    try:
        tenant_id = uuid.UUID(body.tenantId)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant"}})
    if body.amountInrPaise == 0:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_amount", "message": "Amount cannot be zero"}})
    note = (body.note or "").strip()
    if len(note) < 8:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "note_required",
                    "message": "Admin statement required (at least 8 characters) for wallet adjustments.",
                }
            },
        )
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "db_unavailable", "message": "Database required"}})
    if not await tenant_exists(tenant_id):
        raise HTTPException(status_code=404, detail={"error": {"code": "tenant_not_found", "message": "Tenant not found"}})
    kind = admin_adjust_kind(body.amountInrPaise)
    reference_id = admin_adjust_reference(tenant_id, body.amountInrPaise, body.idempotencyKey)
    if await adjustment_already_posted(reference_id):
        return {"ok": True, "duplicate": True, "wallet": await wallet_summary(tenant_id)}
    # The admin's user row belongs to their own workspace, not the target one,
    # so the ledger line carries no user; the audit log names the admin.
    if body.amountInrPaise > 0:
        await credit_wallet(
            tenant_id,
            amount_inr_paise=body.amountInrPaise,
            kind=kind,
            reference_id=reference_id,
        )
    else:
        from server.services.saas.billing_wallet_service import debit_wallet

        await debit_wallet(
            tenant_id,
            kind=kind,
            reference_id=reference_id,
            amount_inr_paise=abs(body.amountInrPaise),
            allow_partial=False,
        )
    from server.services.saas.admin_audit import record_admin_action

    await record_admin_action(
        actor=principal.email,
        action="wallet.platform_adjust",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        payload={
            "amountInrPaise": body.amountInrPaise,
            "kind": kind,
            "referenceId": reference_id,
            "reason": body.reason,
            "note": note,
            "userId": str(principal.user_id),
        },
    )
    return {"ok": True, "wallet": await wallet_summary(tenant_id)}


@router.get("/api/admin/overview")
async def admin_overview(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "db_unavailable", "message": "Database required"}})
    async with factory() as session:
        tenants = int((await session.execute(select(func.count()).select_from(Tenant))).scalar_one() or 0)
        users = int((await session.execute(select(func.count()).select_from(User))).scalar_one() or 0)
        numbers = int(
            (
                await session.execute(
                    select(func.count()).select_from(PhoneNumber).where(PhoneNumber.released_at.is_(None))
                )
            ).scalar_one()
            or 0
        )
        failed = int(
            (
                await session.execute(
                    select(func.count()).select_from(NumberPurchase).where(NumberPurchase.status == "failed")
                )
            ).scalar_one()
            or 0
        )
    wallet = await wallet_summary(principal.tenant_id)
    return {
        "tenants": tenants,
        "users": users,
        "activeNumbers": numbers,
        "failedPurchases": failed,
        "adminWallet": wallet,
        "adminEmail": principal.email,
    }


@router.get("/api/admin/tenants")
async def admin_tenants(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    factory = get_session_factory()
    if factory is None:
        return {"tenants": []}
    # The console shows dollars, but a wallet funded in INR has to be converted.
    # Sending the admin-configured rate means the number on screen is the same
    # one the billing engine charges with, rather than a constant in the UI.
    from server.services.saas.billing_rates import load_current_rates

    fx_rate_inr = float((await load_current_rates())["fx_rate_inr"])
    async with factory() as session:
        rows = (await session.execute(select(Tenant).order_by(Tenant.created_at.desc()).limit(100))).scalars()
        wallets = {
            w.tenant_id: w
            for w in (await session.execute(select(BillingWallet))).scalars()
        }
        out = []
        for t in rows:
            w = wallets.get(t.tenant_id)
            cents = int(w.balance_cents) if w else 0
            paise = int(getattr(w, "balance_inr_paise", 0) or 0) if w else 0
            out.append(
                {
                    "tenantId": str(t.tenant_id),
                    "name": t.name,
                    "plan": t.plan,
                    "status": t.status,
                    "balanceInrPaise": paise,
                    "balanceCents": cents,
                    # USD is the display currency. A USD-funded wallet is used
                    # as-is; an INR-only one is converted at the charge rate.
                    "balanceUsdCents": cents or int(round(paise / 100 / fx_rate_inr * 100)),
                    "fxRateInr": fx_rate_inr,
                }
            )
        return {"tenants": out}


class SwitchTelephonyProviderBody(BaseModel):
    provider: str = Field(..., pattern="^(telnyx|vobiz)$")


@router.post("/api/admin/telephony/provider")
async def admin_set_telephony_provider(
    body: SwitchTelephonyProviderBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Admin route to switch the active telephony infrastructure backend."""
    _require_admin(principal)
    from server.services.dev_secrets_store import dev_secrets_store

    enable_key = f"enable_{body.provider}"
    dev_secrets_store.update({
        "telephony_provider": body.provider,
        enable_key: True,
    })
    return {"ok": True, "activeProvider": body.provider}


class TenantStatusBody(BaseModel):
    status: str = Field(..., pattern="^(active|suspended|past_due|cancelled)$")


@router.patch("/api/admin/tenants/{tenant_id}/status")
async def admin_set_tenant_status(
    tenant_id: str,
    body: TenantStatusBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Block or unblock a subscriber workspace."""
    _require_admin(principal)
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant ID"}},
        )

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "db_unavailable", "message": "Database required"}},
        )

    async with factory() as session:
        t = await session.get(Tenant, tid)
        if not t:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Tenant not found"}},
            )
        # Protect mohan saiteja's Workspace from being suspended or blocked
        if "mohan saiteja" in t.name.lower() and body.status != "active":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "protected_workspace",
                        "message": "Primary workspace [mohan saiteja's Workspace] is protected and cannot be blocked.",
                    }
                },
            )
        t.status = body.status
        await session.commit()
        return {"ok": True, "tenantId": str(t.tenant_id), "status": t.status}


@router.delete("/api/admin/tenants/{tenant_id}")
async def admin_delete_tenant(
    tenant_id: str,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Permanently delete an unnecessary workspace and cascade all child records."""
    _require_admin(principal)
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant ID"}},
        )

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "db_unavailable", "message": "Database required"}},
        )

    async with factory() as session:
        t = await session.get(Tenant, tid)
        if not t:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Tenant not found"}},
            )
        if "mohan saiteja" in t.name.lower():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "protected_workspace",
                        "message": "Primary workspace [mohan saiteja's Workspace] is protected and cannot be deleted.",
                    }
                },
            )

        from server.db.models.saas_models import BillingWallet

        wallet = await session.get(BillingWallet, tid)
        if wallet and (int(wallet.balance_cents or 0) > 0 or int(wallet.balance_inr_paise or 0) > 0):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "wallet_balance_remaining",
                        "message": "Refund or zero the wallet balance before deleting this workspace.",
                    }
                },
            )

    from server.db.connection import get_engine
    from sqlalchemy import text

    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Database engine unavailable")

    from server.services.saas.billing_retention_service import archive_billing_records

    str_tid = str(tid)
    async with engine.begin() as conn:
        # Tax invoices and their ledger outlive the workspace: move them to the
        # archive tenant with buyer contact details erased before the cascade.
        await archive_billing_records(conn, tid)

        # Clear default_agent_id on this tenant first
        await conn.execute(
            text("UPDATE tenants SET default_agent_id = NULL WHERE tenant_id = :tid"),
            {"tid": str_tid},
        )

        # Cascading dependent tables in exact foreign key order
        await conn.execute(
            text(
                "DELETE FROM dial_attempts WHERE campaign_id IN (SELECT campaign_id FROM campaigns WHERE tenant_id = :tid)"
            ),
            {"tid": str_tid},
        )
        await conn.execute(
            text(
                "DELETE FROM campaign_contacts WHERE campaign_id IN (SELECT campaign_id FROM campaigns WHERE tenant_id = :tid)"
            ),
            {"tid": str_tid},
        )
        await conn.execute(
            text(
                "DELETE FROM campaign_runs WHERE campaign_id IN (SELECT campaign_id FROM campaigns WHERE tenant_id = :tid)"
            ),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM campaigns WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM contacts WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM contact_lists WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM contact_import_templates WHERE tenant_id = :tid"),
            {"tid": str_tid},
        )
        await conn.execute(
            text(
                "DELETE FROM provision_jobs WHERE purchase_id IN (SELECT id FROM number_purchases WHERE tenant_id = :tid)"
            ),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM number_reservations WHERE tenant_id = :tid"),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM number_purchases WHERE tenant_id = :tid"),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM phone_numbers WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM call_callbacks WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM call_attempts WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM calls WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text(
                "DELETE FROM business_brain_sections WHERE agent_id IN (SELECT agent_id FROM agents WHERE tenant_id = :tid)"
            ),
            {"tid": str_tid},
        )
        await conn.execute(
            text(
                "DELETE FROM business_brain_versions WHERE agent_id IN (SELECT agent_id FROM agents WHERE tenant_id = :tid)"
            ),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM agent_telephony_profiles WHERE tenant_id = :tid"),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM agent_integrations WHERE tenant_id = :tid"),
            {"tid": str_tid},
        )
        await conn.execute(
            text("DELETE FROM tool_executions WHERE tenant_id = :tid"), {"tid": str_tid}
        )
        await conn.execute(
            text("DELETE FROM agents WHERE tenant_id = :tid"), {"tid": str_tid}
        )

        _TEARDOWN_STATEMENTS = (
            text("DELETE FROM oauth_states WHERE tenant_id = :tid"),
            text("DELETE FROM tenant_integrations WHERE tenant_id = :tid"),
            text("DELETE FROM user_onboarding_surveys WHERE tenant_id = :tid"),
            text("DELETE FROM kyc_verifications WHERE tenant_id = :tid"),
            text("DELETE FROM leads WHERE tenant_id = :tid"),
            text("DELETE FROM billing_wallets WHERE tenant_id = :tid"),
            text("DELETE FROM tenant_billing_profiles WHERE tenant_id = :tid"),
            text("DELETE FROM telephony_contacts WHERE tenant_id = :tid"),
            text("DELETE FROM tenant_teardown_jobs WHERE tenant_id = :tid"),
            text("DELETE FROM dnc_list WHERE tenant_id = :tid"),
            text("DELETE FROM tenant_memberships WHERE tenant_id = :tid"),
        )
        for stmt in _TEARDOWN_STATEMENTS:
            await conn.execute(stmt, {"tid": str_tid})

        await conn.execute(
            text("DELETE FROM tenants WHERE tenant_id = :tid"), {"tid": str_tid}
        )

    return {"ok": True, "deletedTenantId": str_tid}


@router.get("/api/admin/phone-numbers")
async def admin_list_phone_numbers(
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """List all phone numbers currently held across tenants and inventory."""
    _require_admin(principal)
    factory = get_session_factory()
    if factory is None:
        return {"phoneNumbers": []}

    async with factory() as session:
        numbers = (
            await session.execute(
                select(PhoneNumber)
                .where(PhoneNumber.released_at.is_(None))
                .order_by(PhoneNumber.created_at.desc())
            )
        ).scalars().all()

        tenants_map = {
            t.tenant_id: t.name
            for t in (await session.execute(select(Tenant))).scalars().all()
        }
        agents_map = {
            a.agent_id: a.name
            for a in (await session.execute(select(Agent))).scalars().all()
        }

        out = []
        for p in numbers:
            prov = "telnyx" if (getattr(p, "telnyx_number_id", None) and getattr(p, "telnyx_number_id", None) != "carrier_platform") or p.e164 == "+13526146416" else "vobiz"
            if getattr(p, "carrier_number_id", None) or str(p.e164).startswith("+91"):
                prov = "vobiz"

            out.append(
                {
                    "id": str(p.id),
                    "e164": p.e164,
                    "status": p.status,
                    "provider": prov,
                    "tenantId": str(p.tenant_id),
                    "tenantName": tenants_map.get(p.tenant_id, "Unknown"),
                    "agentId": str(p.agent_id) if p.agent_id else None,
                    "agentName": agents_map.get(p.agent_id) if p.agent_id else None,
                    "inboundEnabled": bool(p.inbound_enabled),
                    "outboundEnabled": bool(p.outbound_enabled),
                    "billingSource": p.billing_source,
                    "createdAt": p.created_at.isoformat() if p.created_at else None,
                }
            )
        return {"phoneNumbers": out}


@router.get("/api/admin/phone-numbers/search")
async def admin_search_phone_numbers(
    provider: str = "vobiz",
    country: str = "US",
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Admin route to query available carrier inventory directly from Vobiz or Telnyx."""
    _require_admin(principal)
    prov = provider.lower().strip()
    country_norm = country.upper().strip()

    numbers = []
    try:
        if prov == "vobiz":
            from server.services.vobiz_client import VobizClient

            numbers = await VobizClient().search_available_numbers(
                country=country_norm, limit=15
            )
        else:
            from server.services.telnyx_client import TelnyxClient

            numbers = await TelnyxClient().search_available_numbers(
                country=country_norm, limit=15
            )
    except Exception as exc:
        logger.warning("Admin carrier search failed prov=%s country=%s: %s", prov, country_norm, exc)
        numbers = []

    from server.services.saas.billing_rates import load_current_rates

    rates = await load_current_rates()
    monthly_usd = round(rates["did_monthly_usd_cents"] / 100.0, 2)
    monthly_inr = round(rates["did_monthly_inr_paise"] / 100.0, 2)

    unavailable: set[str] = set()
    factory = get_session_factory()
    if factory is not None:
        async with factory() as session:
            existing = (
                await session.execute(
                    select(PhoneNumber.e164).where(PhoneNumber.released_at.is_(None))
                )
            ).scalars().all()
            for ex in existing:
                if ex:
                    unavailable.add(str(ex).strip())

    cleaned = []
    seen: set[str] = set()
    for item in numbers:
        row = dict(item) if isinstance(item, dict) else {"e164": str(item)}
        e164 = str(row.get("e164") or row.get("phone_number") or "").strip()
        if not e164 or e164 in unavailable or e164 in seen:
            continue
        seen.add(e164)
        row["e164"] = e164
        row["monthlyUsd"] = monthly_usd
        row["monthlyInr"] = monthly_inr
        row["provider"] = prov
        row["country"] = country_norm
        cleaned.append(row)

    return {"numbers": cleaned, "provider": prov, "country": country_norm}


class AdminBuyNumberBody(BaseModel):
    e164: str = Field(..., min_length=8)
    provider: str = Field("vobiz", pattern="^(vobiz|telnyx)$")
    country: str = Field("US", max_length=8)
    tenantId: str | None = None
    assignAgentId: str | None = None


@router.post("/api/admin/phone-numbers/buy")
async def admin_buy_phone_number(
    body: AdminBuyNumberBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Admin route to purchase and provision a phone number directly for a workspace."""
    _require_admin(principal)
    from server.services.saas.number_purchase_service import normalize_e164

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")

    e164 = normalize_e164(body.e164)
    target_tenant_id = None
    if body.tenantId:
        try:
            target_tenant_id = uuid.UUID(body.tenantId)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid target tenant ID")
    else:
        target_tenant_id = principal.tenant_id

    async with factory() as session:
        t = await session.get(Tenant, target_tenant_id)
        if not t:
            raise HTTPException(status_code=404, detail="Target tenant not found")

        # Check if number already registered
        existing = (
            await session.execute(
                select(PhoneNumber).where(
                    PhoneNumber.e164 == e164, PhoneNumber.released_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="This number is already active in the system.")

        bind_agent_id = None
        if body.assignAgentId:
            try:
                ag_uuid = uuid.UUID(body.assignAgentId)
                ag = await session.get(Agent, ag_uuid)
                if ag and ag.tenant_id == target_tenant_id:
                    bind_agent_id = ag.agent_id
            except ValueError:
                pass

    # Order through carrier
    from server.services.telephony import active_telephony_provider
    if body.provider != active_telephony_provider():
        raise HTTPException(status_code=409, detail="inactive_provider")
    from server.services.saas.number_inventory import is_platform_inventory_tenant
    customer_account = body.provider == "vobiz" and not is_platform_inventory_tenant(t)
    if customer_account:
        from server.services.saas.voice_kyc_service import assert_voice_kyc_approved
        await assert_voice_kyc_approved(target_tenant_id, action="activate a phone number")
    async with factory() as session:
        from sqlalchemy.exc import IntegrityError
        reservation = PhoneNumber(
            tenant_id=target_tenant_id, e164=e164, status="provisioning", billing_source="admin",
            inbound_enabled=False, outbound_enabled=False, agent_id=bind_agent_id,
            vobiz_account_scope="tenant" if customer_account else None,
            vobiz_account_tenant_id=target_tenant_id if customer_account else None,
        )
        session.add(reservation)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail="number_already_active") from None
        reservation_id = reservation.id
    carrier_res = {}
    try:
        if body.provider == "vobiz":
            from server.services.vobiz_client import VobizClient

            if customer_account:
                from server.services.saas.voice_kyc_service import provision_tenant_number
                carrier_res = await provision_tenant_number(target_tenant_id, e164)
            else:
                carrier_res = await VobizClient().provision_ordered_number(e164)
        else:
            from server.services.telnyx_client import TelnyxClient
            from server.services.telnyx_provisioning import provision_ordered_number

            client = TelnyxClient()
            carrier_res = await provision_ordered_number(client, e164)
    except Exception as exc:
        logger.warning("Admin carrier order requires reconciliation error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "carrier_order_failed",
                    "message": "Carrier confirmation is pending. Reconcile the reserved number before retrying.",
                }
            },
        )

    # Persist in DB
    async with factory() as session:
        pn = await session.get(PhoneNumber, reservation_id, with_for_update=True)
        real_id = carrier_res.get("phone_number_id")
        pn.status = "active" if real_id else "pending"
        pn.telnyx_number_id = real_id if body.provider == "telnyx" else None
        pn.carrier_number_id = real_id if body.provider == "vobiz" else None
        pn.inbound_enabled = pn.outbound_enabled = bool(real_id)
        await session.commit()
        await session.refresh(pn)
        pn_id = str(pn.id)

    return {
        "ok": True,
        "id": pn_id,
        "e164": e164,
        "provider": body.provider,
        "tenantId": str(target_tenant_id),
        "agentId": str(bind_agent_id) if bind_agent_id else None,
    }


@router.delete("/api/admin/phone-numbers/{number_id}")
async def admin_delete_phone_number(
    number_id: str,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Admin releases/deletes a platform phone line."""
    _require_admin(principal)
    try:
        nid = uuid.UUID(number_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid phone number ID")

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")

    from datetime import datetime, timezone

    async with factory() as session:
        pn = await session.get(PhoneNumber, nid)
        if not pn:
            raise HTTPException(status_code=404, detail="Phone number not found")
        if pn.vobiz_account_scope == "tenant":
            from server.services.saas.number_inventory import move_to_inventory
            result = await move_to_inventory(number_id=nid)
            return {"ok": True, "released": number_id, "status": result["status"]}
        pn.released_at = datetime.now(timezone.utc)
        pn.status = "released"
        pn.agent_id = None
        await session.commit()

    return {"ok": True, "released": number_id}


class AdminTestCallBody(BaseModel):
    to_e164: str = Field(..., min_length=8)
    from_e164: str | None = None
    provider: str = Field("vobiz")


@router.post("/api/admin/telephony/test-call")
async def admin_telephony_test_call(
    body: AdminTestCallBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Admin route to initiate a live test call through Vobiz or Telnyx trunk."""
    _require_admin(principal)
    prov = body.provider.lower().strip()
    to_num = body.to_e164.strip()
    from_num = (body.from_e164 or "").strip()

    if prov == "vobiz":
        from server.services.vobiz_client import VobizClient, vobiz_call_registry, vobiz_stream_tokens
        from server.config.urls import public_api_base
        import time

        client = VobizClient()
        caller_id = from_num or client.cfg.get("phone_number")
        if not caller_id:
            raise HTTPException(status_code=400, detail="caller_id_required")
        account_scope = "platform"
        account_tenant_id = None
        factory = get_session_factory()
        if factory:
            async with factory() as db:
                number = (await db.execute(select(PhoneNumber).where(
                    PhoneNumber.e164 == caller_id, PhoneNumber.released_at.is_(None),
                ))).scalar_one_or_none()
            if number and number.vobiz_account_scope == "tenant":
                from server.services.saas.voice_kyc_service import assert_voice_kyc_approved, vobiz_client_for_number
                account_tenant_id = str(number.vobiz_account_tenant_id or number.tenant_id)
                await assert_voice_kyc_approved(uuid.UUID(account_tenant_id), action="place a phone call")
                client, account_scope = await vobiz_client_for_number(number.tenant_id, caller_id)
        base_api = public_api_base()
        tracking_id = f"admin-vobiz-{uuid.uuid4()}"

        token = vobiz_stream_tokens.create(
            call_uuid=tracking_id,
            direction="outbound",
            outbound_id=tracking_id,
            vobiz_account_scope=account_scope,
            vobiz_account_tenant_id=account_tenant_id,
        )

        ans_url = f"{base_api}/api/vobiz/answer?token={token}&outbound_id={tracking_id}"
        hup_url = f"{base_api}/api/vobiz/hangup?token={token}&outbound_id={tracking_id}"
        fallback_url = f"{base_api}/api/vobiz/fallback?token={token}&outbound_id={tracking_id}"

        vobiz_call_registry.upsert(
            tracking_id,
            {
                "call_uuid": tracking_id,
                "outbound_id": tracking_id,
                "to": to_num,
                "from": caller_id,
                "direction": "outbound",
                "status": "initiated",
                "dialed_at": time.time(),
                "provider": "vobiz",
                "vobiz_account_scope": account_scope,
                "vobiz_account_tenant_id": account_tenant_id,
                "token": token,
            },
        )

        try:
            res = await client.create_outbound_call(
                to=to_num,
                from_=caller_id,
                answer_url=ans_url,
                hangup_url=hup_url,
                fallback_url=fallback_url,
            )
            carrier_uuid = str(
                res.get("call_uuid")
                or res.get("request_uuid")
                or res.get("id")
                or res.get("api_id")
                or ""
            )
            effective_id = carrier_uuid or tracking_id

            if carrier_uuid and carrier_uuid != tracking_id:
                vobiz_call_registry.alias(carrier_uuid, tracking_id)
                vobiz_call_registry.upsert(
                    carrier_uuid,
                    {
                        "call_uuid": carrier_uuid,
                        "outbound_id": tracking_id,
                        "to": to_num,
                        "from": caller_id,
                        "direction": "outbound",
                        "status": "initiated",
                        "token": token,
                    },
                )

            return {
                "ok": True,
                "provider": "vobiz",
                "call_uuid": effective_id,
                "to": to_num,
                "from": caller_id,
                "status": "initiated",
                "details": res,
            }
        except Exception as exc:
            logger.exception("Admin Vobiz test call failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "carrier_call_failed", "message": str(exc)[:300]}},
            )
    else:
        from server.services.telnyx_client import TelnyxClient
        client = TelnyxClient()
        caller_id = from_num or client.phone_number
        try:
            res = await client.create_outbound_call(to=to_num, from_=caller_id)
            return {
                "ok": True,
                "provider": "telnyx",
                "call_uuid": str(res.get("call_control_id") or uuid.uuid4()),
                "to": to_num,
                "from": caller_id,
                "status": "initiated",
                "details": res,
            }
        except Exception as exc:
            logger.exception("Admin Telnyx test call failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "carrier_call_failed", "message": str(exc)[:300]}},
            )


# -----------------------------------------------------------------------------
# Customer Support Flow & Inquiry Management (Platform Admin)
# -----------------------------------------------------------------------------

class AdminSupportConfigBody(BaseModel):
    supportEmail: str | None = None
    businessHours: str | None = None
    slaResponseTime: str | None = None
    autoReplyMessage: str | None = None
    isActive: bool | None = None
    twitterUrl: str | None = None
    linkedinUrl: str | None = None
    githubUrl: str | None = None
    youtubeUrl: str | None = None
    discordUrl: str | None = None
    smtpHost: str | None = None
    smtpPort: int | None = None
    smtpUsername: str | None = None
    smtpPassword: str | None = None
    smtpUseTls: bool | None = None
    senderEmail: str | None = None
    senderName: str | None = None
    notifyCustomerOnTicket: bool | None = None
    notifyAdminOnTicket: bool | None = None
    adminAlertEmail: str | None = None


class AdminTestSmtpBody(BaseModel):
    smtpHost: str | None = None
    smtpPort: int | None = 587
    smtpUsername: str | None = None
    smtpPassword: str | None = None
    smtpUseTls: bool | None = True


class AdminUpdateInquiryBody(BaseModel):
    status: str | None = None
    assignedTo: str | None = None
    adminNotes: str | None = None
    resolutionNotes: str | None = None
    replyMessage: str | None = None
    tags: list[str] | None = None


@router.get("/api/admin/support/config")
async def admin_get_support_config(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    from server.services.saas.customer_support_service import get_support_config
    config = await get_support_config(for_admin=True)
    return {"ok": True, "config": config}


@router.put("/api/admin/support/config")
async def admin_update_support_config(body: AdminSupportConfigBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    from server.services.saas.customer_support_service import update_support_config
    updates = body.model_dump(exclude_unset=True)
    updated = await update_support_config(updates)
    return {"ok": True, "config": updated}


@router.post("/api/admin/support/smtp/test")
async def admin_test_smtp_connection(body: AdminTestSmtpBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    _require_admin(principal)
    from server.services.saas.customer_support_service import test_smtp_configuration
    res = await test_smtp_configuration(body.model_dump(exclude_unset=True))
    if not res.get("success"):
        raise HTTPException(status_code=400, detail={"error": {"code": "smtp_test_failed", "message": res.get("error")}})
    return {"ok": True, "message": res.get("message")}


@router.get("/api/admin/support/inquiries")
async def admin_list_support_inquiries(
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    _require_admin(principal)
    from server.services.saas.customer_support_service import list_support_inquiries
    inquiries = await list_support_inquiries(
        status=status,
        priority=priority,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "inquiries": inquiries}


@router.get("/api/admin/support/inquiries/{inquiry_id}")
async def admin_get_support_inquiry(
    inquiry_id: str,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    _require_admin(principal)
    from server.services.saas.customer_support_service import get_support_inquiry_detail
    try:
        inq_uuid = uuid.UUID(inquiry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_id", "message": "Invalid inquiry ID"}})
    detail = await get_support_inquiry_detail(inq_uuid)
    if not detail:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Inquiry not found"}})
    return {"ok": True, "inquiry": detail}


@router.patch("/api/admin/support/inquiries/{inquiry_id}")
async def admin_update_support_inquiry(
    inquiry_id: str,
    body: AdminUpdateInquiryBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    _require_admin(principal)
    from server.services.saas.customer_support_service import update_support_inquiry
    try:
        inq_uuid = uuid.UUID(inquiry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_id", "message": "Invalid inquiry ID"}})
    try:
        updated = await update_support_inquiry(
            inquiry_id=inq_uuid,
            status=body.status,
            assigned_to=body.assignedTo,
            admin_notes=body.adminNotes,
            resolution_notes=body.resolutionNotes,
            reply_message=body.replyMessage,
            reply_author=principal.email or "Support Desk",
            tags=body.tags,
        )
        return {"ok": True, "inquiry": updated}
    except ValueError as err:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": str(err)}})



