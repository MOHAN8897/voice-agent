"""Usage ledger: tenant wallet, per-user attribution, PSTN / web / DID debits."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_user_id(raw: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


async def get_or_create_wallet(tenant_id: uuid.UUID) -> BillingWallet:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, updated_at=_utcnow())
            session.add(wallet)
            await session.commit()
            await session.refresh(wallet)
        return wallet


async def wallet_summary(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict:
    from server.services.saas.billing_rates import load_current_rates

    settings = get_settings()
    rates = await load_current_rates()
    wallet = await get_or_create_wallet(tenant_id)
    inr_paise = int(getattr(wallet, "balance_inr_paise", 0) or 0)
    cents = int(wallet.balance_cents or 0)
    primary = (wallet.currency or "usd").lower()
    fx = float(rates.get("fx_rate_inr") or 95.64) or 95.64
    usd_from_cents = cents / 100.0
    usd_from_inr = (inr_paise / 100.0) / fx if fx else 0.0
    # Combined purchasing power so no balance is omitted or hidden
    balance_usd = round(usd_from_cents + usd_from_inr, 2)
    inr_from_paise = inr_paise / 100.0
    inr_from_cents = (cents / 100.0) * fx if fx else 0.0
    balance_inr = round(inr_from_paise + inr_from_cents, 2)

    rate_inr = rates["pstn_rate_inr_paise_per_min"] or 900
    rate_usd_micros = max(1, rates["pstn_rate_usd_micros_per_min"])
    min_from_cents = int((cents * 10_000) // rate_usd_micros) if rate_usd_micros > 0 else 0
    min_from_paise = int(inr_paise // rate_inr) if rate_inr > 0 else 0
    remaining_min = min_from_cents + min_from_paise
    tier_rates_map = {
        "low": {
            "usdPerMin": round(rates["pstn_low_rate_usd_micros_per_min"] / 1_000_000.0, 6) if rates.get("pstn_low_rate_usd_micros_per_min") else None,
            "inrPerMin": round(rates["pstn_low_rate_inr_paise_per_min"] / 100.0, 2) if rates.get("pstn_low_rate_inr_paise_per_min") else None,
        },
        "medium": {
            "usdPerMin": round(rates["pstn_medium_rate_usd_micros_per_min"] / 1_000_000.0, 6) if rates.get("pstn_medium_rate_usd_micros_per_min") else None,
            "inrPerMin": round(rates["pstn_medium_rate_inr_paise_per_min"] / 100.0, 2) if rates.get("pstn_medium_rate_inr_paise_per_min") else None,
        },
        "premium": {
            "usdPerMin": round(rates["pstn_premium_rate_usd_micros_per_min"] / 1_000_000.0, 6) if rates.get("pstn_premium_rate_usd_micros_per_min") else round(rates["pstn_rate_usd_micros_per_min"] / 1_000_000.0, 6),
            "inrPerMin": round(rates["pstn_premium_rate_inr_paise_per_min"] / 100.0, 2) if rates.get("pstn_premium_rate_inr_paise_per_min") else round(rates["pstn_rate_inr_paise_per_min"] / 100.0, 2),
        },
    }
    try:
        from server.services.dev_runtime import effective_app_environment
        from server.services.saas.voice_stack_profiles import load_profile_records, _native_tier_retail_rate
        env = effective_app_environment()
        records = await load_profile_records(env, None)
        for t, rec in records.items():
            t_rate = _native_tier_retail_rate(rates, t, record=rec)
            if t_rate and t_rate.get("inrPaisePerMin"):
                tier_rates_map[t] = {
                    "usdPerMin": round(t_rate["usdMicrosPerMin"] / 1_000_000.0, 6) if t_rate.get("usdMicrosPerMin") else None,
                    "inrPerMin": round(t_rate["inrPaisePerMin"] / 100.0, 2),
                }
    except Exception as exc:
        logger.debug("[WALLET] tier rate overlay error: %s", exc)

    summary = {
        # USD everywhere: the console quotes and displays one currency only.
        "currency": "USD",
        "balanceUsd": balance_usd,
        "balance_usd": balance_usd,
        "balanceCents": cents,
        "balanceInr": balance_inr,
        "balance_inr": balance_inr,
        "balanceInrPaise": inr_paise,
        "walletCurrency": (wallet.currency or "usd").upper(),
        "primaryCurrency": primary,
        "tenantId": str(tenant_id),
        "minBalanceUsd": round(getattr(settings, "pstn_min_balance_usd_cents", 100) / 100.0, 2),
        "minBalanceInr": round(getattr(settings, "pstn_min_balance_inr_paise", 5000) / 100.0, 2),
        "rateUsdPerMin": round(rates["pstn_rate_usd_micros_per_min"] / 1_000_000.0, 6),
        "rateInrPerMin": round(rates["pstn_rate_inr_paise_per_min"] / 100.0, 2),
        "pstnLowRateUsdPerMin": round(rates["pstn_low_rate_usd_micros_per_min"] / 1_000_000.0, 6) if rates.get("pstn_low_rate_usd_micros_per_min") else None,
        "pstnLowRateInrPerMin": round(rates["pstn_low_rate_inr_paise_per_min"] / 100.0, 2) if rates.get("pstn_low_rate_inr_paise_per_min") else None,
        "pstnMediumRateUsdPerMin": round(rates["pstn_medium_rate_usd_micros_per_min"] / 1_000_000.0, 6) if rates.get("pstn_medium_rate_usd_micros_per_min") else None,
        "pstnMediumRateInrPerMin": round(rates["pstn_medium_rate_inr_paise_per_min"] / 100.0, 2) if rates.get("pstn_medium_rate_inr_paise_per_min") else None,
        "pstnPremiumRateUsdPerMin": round(rates["pstn_premium_rate_usd_micros_per_min"] / 1_000_000.0, 6) if rates.get("pstn_premium_rate_usd_micros_per_min") else round(rates["pstn_rate_usd_micros_per_min"] / 1_000_000.0, 6),
        "pstnPremiumRateInrPerMin": round(rates["pstn_premium_rate_inr_paise_per_min"] / 100.0, 2) if rates.get("pstn_premium_rate_inr_paise_per_min") else round(rates["pstn_rate_inr_paise_per_min"] / 100.0, 2),
        "tierRates": tier_rates_map,
        "webRateUsdPerMin": round(rates["web_agent_rate_usd_micros_per_min"] / 1_000_000.0, 6),
        "webRateInrPerMin": round(rates["web_agent_rate_inr_paise_per_min"] / 100.0, 2),
        "didMonthlyUsd": round(rates["did_monthly_usd_micros"] / 1_000_000.0, 6),
        "didMonthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
        "fxRateInr": fx,
        "remainingMinutes": remaining_min,
        "myUsageInr": 0.0,
        "myUsageUsd": 0.0,
        "myUsagePaise": 0,
    }
    if user_id is not None:
        factory = get_session_factory()
        if factory is not None:
            async with factory() as session:
                spent_paise = (
                    await session.execute(
                        select(func.coalesce(func.sum(BillingWalletTransaction.amount_inr_paise), 0)).where(
                            BillingWalletTransaction.tenant_id == tenant_id,
                            BillingWalletTransaction.user_id == user_id,
                            BillingWalletTransaction.amount_inr_paise < 0,
                        )
                    )
                ).scalar_one()
                spent_cents = (
                    await session.execute(
                        select(func.coalesce(func.sum(BillingWalletTransaction.amount_cents), 0)).where(
                            BillingWalletTransaction.tenant_id == tenant_id,
                            BillingWalletTransaction.user_id == user_id,
                            BillingWalletTransaction.amount_cents < 0,
                        )
                    )
                ).scalar_one()
                paise = abs(int(spent_paise or 0))
                cents = abs(int(spent_cents or 0))
                summary["myUsagePaise"] = paise
                summary["myUsageCents"] = cents
                summary["myUsageInr"] = round(paise / 100.0 + ((cents / 100.0) * fx if fx else 0.0), 2)
                summary["myUsageUsd"] = round(cents / 100.0 + ((paise / 100.0) / fx if fx else 0.0), 2)
    return summary


async def list_wallet_transactions(tenant_id: uuid.UUID, limit: int = 50, user_id: uuid.UUID | None = None) -> list[dict]:
    factory = get_session_factory()
    if factory is None:
        return []
    limit = max(1, min(limit, 200))
    async with factory() as session:
        stmt = select(BillingWalletTransaction).where(BillingWalletTransaction.tenant_id == tenant_id)
        if user_id is not None:
            stmt = stmt.where(BillingWalletTransaction.user_id == user_id)
        result = await session.execute(stmt.order_by(BillingWalletTransaction.created_at.desc()).limit(limit))
        txs = list(result.scalars())
        if not txs:
            return []

        from server.db.models.saas_models import BillingWallet
        wallet = await session.get(BillingWallet, tenant_id)
        wallet_currency = getattr(wallet, "currency", "usd")

        # Collect call UUIDs for enriched lookup
        call_ids: list[uuid.UUID] = []
        for tx in txs:
            if tx.reference_id and tx.reference_id.startswith("call:"):
                raw_cid = tx.reference_id.split(":", 1)[1].strip()
                try:
                    call_ids.append(uuid.UUID(raw_cid))
                except (ValueError, TypeError):
                    pass

        calls_by_id: dict[uuid.UUID, Any] = {}
        campaigns_by_id: dict[uuid.UUID, str] = {}
        agents_by_id: dict[uuid.UUID, str] = {}

        if call_ids:
            try:
                from server.db.models.entities import Agent, Call
                from server.db.models.phase5_models import Campaign

                calls_res = await session.execute(
                    select(Call).where(
                        Call.tenant_id == tenant_id,
                        Call.call_id.in_(call_ids),
                    )
                )
                for c in calls_res.scalars():
                    calls_by_id[c.call_id] = c

                camp_ids = [c.campaign_id for c in calls_by_id.values() if c.campaign_id]
                if camp_ids:
                    camps_res = await session.execute(
                        select(Campaign).where(
                            Campaign.tenant_id == tenant_id,
                            Campaign.campaign_id.in_(camp_ids),
                        )
                    )
                    for camp in camps_res.scalars():
                        campaigns_by_id[camp.campaign_id] = camp.name

                agent_ids = [c.agent_id for c in calls_by_id.values() if c.agent_id]
                if agent_ids:
                    agents_res = await session.execute(
                        select(Agent).where(
                            Agent.tenant_id == tenant_id,
                            Agent.agent_id.in_(agent_ids),
                        )
                    )
                    for ag in agents_res.scalars():
                        agents_by_id[ag.agent_id] = ag.name
            except Exception as exc:
                logger.debug("list_wallet_transactions: call enrichment failed: %s", exc)

        rows = []
        for tx in txs:
            call_obj = None
            if tx.reference_id and tx.reference_id.startswith("call:"):
                try:
                    cid = uuid.UUID(tx.reference_id.split(":", 1)[1].strip())
                    call_obj = calls_by_id.get(cid)
                except Exception:
                    pass

            desc = None
            duration_sec = None
            direction = None
            is_campaign = False
            campaign_name = None
            agent_name = None

            if call_obj:
                duration_sec = call_obj.duration_sec
                direction = call_obj.direction
                agent_name = agents_by_id.get(call_obj.agent_id)
                dur_str = f"{duration_sec}s" if duration_sec is not None else ""
                if call_obj.channel == "browser" or getattr(call_obj, "is_test", False) or tx.kind in ("usage_web", "usage_web_test"):
                    ag_label = f": {agent_name}" if agent_name else ""
                    desc = f"Browser Voice Test{ag_label} ({dur_str})" if dur_str else f"Browser Voice Test{ag_label}"
                elif call_obj.campaign_id:
                    is_campaign = True
                    campaign_name = campaigns_by_id.get(call_obj.campaign_id)
                    camp_label = f": {campaign_name}" if campaign_name else ""
                    desc = f"Outbound Campaign{camp_label} ({dur_str})" if dur_str else f"Outbound Campaign{camp_label}"
                elif call_obj.direction == "outbound":
                    ag_label = f": {agent_name}" if agent_name else ""
                    desc = f"Outbound Call{ag_label} ({dur_str})" if dur_str else f"Outbound Call{ag_label}"
                elif call_obj.direction == "inbound":
                    ag_label = f": {agent_name}" if agent_name else ""
                    desc = f"Inbound Call{ag_label} ({dur_str})" if dur_str else f"Inbound Call{ag_label}"
                else:
                    desc = f"Voice Call ({dur_str})" if dur_str else "Voice Call"

            if (not call_obj or duration_sec is None) and tx.reference_id and tx.reference_id.startswith("call:"):
                raw_cid = tx.reference_id.split(":", 1)[1].strip()
                try:
                    from server.call.call_ledger import call_ledger
                    meta = call_ledger.read_meta(raw_cid)
                    if meta:
                        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
                        dur = usage.get("duration_sec") if usage.get("duration_sec") is not None else meta.get("duration_sec")
                        if dur is not None and duration_sec is None:
                            duration_sec = int(dur)
                        if not agent_name and meta.get("agent_id"):
                            try:
                                ag_uuid = uuid.UUID(str(meta.get("agent_id")))
                                agent_name = agents_by_id.get(ag_uuid)
                            except Exception:
                                pass
                        if not direction and meta.get("direction"):
                            direction = str(meta.get("direction"))
                        ch = str(meta.get("channel") or ("browser" if tx.kind in ("usage_web", "usage_web_test") else ""))
                        dur_str = f"{duration_sec}s" if duration_sec is not None else ""
                        if ch == "browser" or tx.kind in ("usage_web", "usage_web_test"):
                            ag_label = f": {agent_name}" if agent_name else ""
                            desc = f"Browser Voice Test{ag_label} ({dur_str})" if dur_str else f"Browser Voice Test{ag_label}"
                        elif direction:
                            ag_label = f": {agent_name}" if agent_name else ""
                            desc = f"{direction.title()} Call{ag_label} ({dur_str})" if dur_str else f"{direction.title()} Call{ag_label}"
                except Exception:
                    pass

            if not desc:
                dur_str = f"{duration_sec}s" if duration_sec is not None else ""
                if tx.kind in ("topup", "razorpay_topup_inr", "razorpay_topup"):
                    desc = "Wallet Recharge / Top-up"
                elif tx.kind == "admin_seed":
                    desc = "Welcome credits / Seed balance"
                elif tx.kind == "did_purchase":
                    desc = "Phone number provisioning"
                elif tx.kind == "did_refund":
                    desc = "Phone number release refund"
                elif tx.kind in ("admin_grant", "admin_debit"):
                    desc = "Manual balance adjustment"
                elif tx.kind == "forfeiture":
                    desc = "Account deletion forfeiture"
                elif tx.kind == "usage_pstn":
                    ag_label = f": {agent_name}" if agent_name else ""
                    desc = f"Phone Call{ag_label} ({dur_str})" if dur_str else "Phone call usage"
                elif tx.kind in ("usage_web", "usage_web_test"):
                    ag_label = f": {agent_name}" if agent_name else ""
                    desc = f"Browser Voice Test{ag_label} ({dur_str})" if dur_str else "Browser Voice Test"
                else:
                    desc = tx.kind.replace("_", " ").title()

            call_fx = getattr(call_obj, "applied_fx_rate_inr", None) if call_obj else None
            tier = getattr(call_obj, "tier", None) if call_obj else None
            if not tier and tx.reference_id and tx.reference_id.startswith("call:"):
                raw_cid = tx.reference_id.split(":", 1)[1].strip()
                try:
                    from server.call.call_ledger import call_ledger
                    meta = call_ledger.read_meta(raw_cid)
                    if meta and meta.get("tier"):
                        tier = str(meta.get("tier"))
                except Exception:
                    pass
                if not tier:
                    try:
                        from server.call.call_store import call_store
                        stored_c = await call_store.get(raw_cid)
                        if stored_c and stored_c.get("tier"):
                            tier = str(stored_c.get("tier"))
                    except Exception:
                        pass

            tier_label = {
                "low": "Economical Tier",
                "medium": "Standard Regional Tier",
                "premium": "Flagship Live Tier",
            }.get(tier, tier.title() if tier else None)

            display_charge = wallet_debit_display(
                amount_cents=tx.amount_cents,
                amount_inr_paise=tx.amount_inr_paise,
                wallet_currency=wallet_currency,
                fx_rate_inr=call_fx or get_settings().fx_rate_inr,
            )
            rows.append(
                {
                    "id": str(tx.id),
                    "kind": tx.kind,
                    "amountCents": tx.amount_cents,
                    "amountInrPaise": int(tx.amount_inr_paise or 0),
                    "displayAmount": display_charge["amount"],
                    "displayCurrency": display_charge["currency"],
                    "referenceId": tx.reference_id,
                    "userId": str(tx.user_id) if tx.user_id else None,
                    "createdAt": tx.created_at.isoformat() if tx.created_at else None,
                    "description": desc,
                    "durationSec": duration_sec,
                    "direction": direction,
                    "isCampaign": is_campaign,
                    "campaignName": campaign_name,
                    "agentName": agent_name,
                    "tier": tier,
                    "tierLabel": tier_label,
                }
            )
        return rows


def _wallet_has_minimum(wallet: BillingWallet) -> bool:
    """True if either INR or USD balance clears the configured floor, or combined equivalent clears it.

    Razorpay top-ups credit INR only; wallets often still have currency='usd'.
    Checking both sides avoids blocking paid tenants after an INR top-up.
    """
    settings = get_settings()
    fx = float(getattr(settings, "fx_rate_inr", 0) or 95.64) or 95.64
    inr_paise = int(wallet.balance_inr_paise or 0)
    usd_cents = int(wallet.balance_cents or 0)
    if inr_paise >= settings.pstn_min_balance_inr_paise or usd_cents >= settings.pstn_min_balance_usd_cents:
        return True
    combined_cents = usd_cents + (inr_paise / fx if fx > 0 else 0)
    if combined_cents >= settings.pstn_min_balance_usd_cents:
        return True
    combined_paise = inr_paise + (usd_cents * fx)
    if combined_paise >= settings.pstn_min_balance_inr_paise:
        return True
    return False


async def assert_wallet_allows_pstn(tenant_id: uuid.UUID) -> None:
    """Block billed voice when balance is below configured minimum."""
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return
    wallet = await get_or_create_wallet(tenant_id)
    if not _wallet_has_minimum(wallet):
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "insufficient_balance",
                    "message": "Add funds to your wallet before using voice minutes.",
                }
            },
        )


assert_wallet_allows_usage = assert_wallet_allows_pstn


async def max_allowed_call_duration_sec(
    tenant_id: uuid.UUID,
    channel: str = "pstn",
    global_cap_sec: int = 900,
) -> int:
    """Calculate maximum duration in seconds that the tenant's wallet balance can cover.

    Caps at global_cap_sec (default 900s / 15 mins). If SaaS auth is disabled, returns global_cap_sec.
    """
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return global_cap_sec
    try:
        wallet = await get_or_create_wallet(tenant_id)
    except Exception:
        return global_cap_sec

    rate_cents = int(settings.pstn_rate_usd_cents_per_min if channel == "pstn" else settings.web_agent_rate_usd_cents_per_min)
    rate_cents = max(1, rate_cents)
    rate_cents_per_sec = rate_cents / 60.0

    fx = float(getattr(settings, "fx_rate_inr", 0) or 95.64) or 95.64
    rate_paise_per_sec = max(0.01, (rate_cents * fx) / 60.0)

    balance_cents = max(0, int(wallet.balance_cents or 0))
    balance_paise = max(0, int(wallet.balance_inr_paise or 0))

    dur_usd = int(balance_cents / rate_cents_per_sec) if balance_cents > 0 else 0
    dur_inr = int(balance_paise / rate_paise_per_sec) if balance_paise > 0 else 0
    affordable_sec = dur_usd + dur_inr

    return min(global_cap_sec, max(0, affordable_sec))


async def assert_wallet_can_afford_did(tenant_id: uuid.UUID) -> None:
    """Fail fast before inventory transfer or Telnyx order when the wallet cannot cover monthly DID rent."""
    from server.services.saas.billing_rates import load_current_rates

    rates = await load_current_rates()
    want_cents = int(rates["did_monthly_usd_cents"])
    want_paise = int(rates["did_monthly_inr_paise"])
    wallet = await get_or_create_wallet(tenant_id)
    have_cents = int(wallet.balance_cents or 0)
    have_paise = int(wallet.balance_inr_paise or 0)
    if have_cents >= want_cents or have_paise >= want_paise:
        return
    raise ValueError("insufficient_balance")


async def wallet_allows_inbound(tenant_id: uuid.UUID | None) -> bool:
    """Whether inbound calls should be answered for this tenant.

    Returns a decision, never raises: the caller is on the live PSTN answer path,
    where an exception or a slow query must not drop a customer's call. On any
    internal error this returns True, which matches the pre-wallet behaviour of
    answering everything.
    """
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return True
    if not settings.pstn_enforce_wallet_on_inbound:
        return True
    if tenant_id is None:
        return True
    try:
        wallet = await get_or_create_wallet(tenant_id)
    except Exception:
        logger.warning("[WALLET] inbound balance check failed; answering (fail open)")
        return True
    allowed = _wallet_has_minimum(wallet)
    if not allowed:
        logger.info(
            "[WALLET] inbound blocked tenant=%s below minimum usd_cents=%s inr_paise=%s",
            tenant_id,
            settings.pstn_min_balance_usd_cents,
            settings.pstn_min_balance_inr_paise,
        )
    return allowed


async def maybe_seed_admin_credits(tenant_id: uuid.UUID, user_id: uuid.UUID, email: str) -> None:
    from server.services.saas.platform_admins import is_platform_admin_email, is_dev_tester_email

    settings = get_settings()
    if not (is_platform_admin_email(email) or is_dev_tester_email(email)):
        return
    seed = int(settings.saas_admin_seed_inr_paise or 0)
    if seed <= 0:
        return
    ref = f"admin_seed:{tenant_id}"
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        dup = await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == ref)
        )
        if dup.scalar_one_or_none():
            return
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, currency="inr", updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        wallet.currency = "inr"
        wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + seed
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=0,
                amount_inr_paise=seed,
                kind="admin_seed",
                reference_id=ref,
                created_at=_utcnow(),
            )
        )
        await session.commit()
    logger.info("[WALLET] seeded admin credits tenant=%s paise=%s", tenant_id, seed)


async def credit_wallet(
    tenant_id: uuid.UUID,
    *,
    amount_cents: int = 0,
    amount_inr_paise: int = 0,
    kind: str,
    reference_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        if reference_id:
            dup = await session.execute(
                select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == reference_id)
            )
            if dup.scalar_one_or_none():
                return
        wallet = await session.get(BillingWallet, tenant_id, with_for_update=True)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        if amount_inr_paise:
            wallet.currency = wallet.currency or "inr"
            wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + int(amount_inr_paise)
        if amount_cents:
            wallet.balance_cents = int(wallet.balance_cents or 0) + int(amount_cents)
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=int(amount_cents),
                amount_inr_paise=int(amount_inr_paise),
                kind=kind,
                reference_id=reference_id,
                created_at=_utcnow(),
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return


async def debit_wallet(
    tenant_id: uuid.UUID,
    *,
    kind: str,
    reference_id: str,
    user_id: uuid.UUID | None = None,
    amount_cents: int = 0,
    amount_inr_paise: int = 0,
    fx_rate_inr_override: float | None = None,
    allow_partial: bool = True,
) -> dict:
    """Atomic debit. Raises 402 if empty and not allow_partial."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        dup = await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == reference_id)
        )
        if dup.scalar_one_or_none():
            return {"ok": True, "duplicate": True, "amountCents": 0, "amountInrPaise": 0}
        wallet = await session.get(BillingWallet, tenant_id, with_for_update=True)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        have_cents = int(wallet.balance_cents or 0)
        have_paise = int(wallet.balance_inr_paise or 0)
        primary = (wallet.currency or "usd").lower()
        try:
            fx = float(fx_rate_inr_override or getattr(get_settings(), "fx_rate_inr", 0) or 95.64)
        except (TypeError, ValueError):
            fx = 95.64
        if fx <= 0:
            fx = 95.64

        want_cents = abs(int(amount_cents))
        want_paise = abs(int(amount_inr_paise))

        if want_cents == 0 and want_paise > 0 and fx > 0:
            want_cents = max(1, int(round(want_paise / fx)))
        elif want_paise == 0 and want_cents > 0 and fx > 0:
            want_paise = max(1, int(round(want_cents * fx)))

        debit_cents = 0
        debit_paise = 0

        if primary == "inr":
            if have_paise >= want_paise:
                debit_paise = want_paise
            elif have_cents >= want_cents:
                debit_cents = want_cents
            else:
                total_avail_paise = have_paise + int(round(have_cents * fx))
                if total_avail_paise < want_paise and not allow_partial:
                    raise HTTPException(
                        status_code=402,
                        detail={"error": {"code": "insufficient_balance", "message": "Not enough wallet credits."}},
                    )
                debit_paise = min(have_paise, want_paise)
                rem_paise = want_paise - debit_paise
                if rem_paise > 0 and have_cents > 0:
                    needed_cents = max(1, int(round(rem_paise / fx)))
                    debit_cents = min(have_cents, needed_cents)
        else:
            if have_cents >= want_cents:
                debit_cents = want_cents
            elif have_paise >= want_paise:
                debit_paise = want_paise
            else:
                total_avail_cents = have_cents + int(round(have_paise / fx))
                if total_avail_cents < want_cents and not allow_partial:
                    raise HTTPException(
                        status_code=402,
                        detail={"error": {"code": "insufficient_balance", "message": "Not enough wallet credits."}},
                    )
                debit_cents = min(have_cents, want_cents)
                rem_cents = want_cents - debit_cents
                if rem_cents > 0 and have_paise > 0:
                    needed_paise = max(1, int(round(rem_cents * fx)))
                    debit_paise = min(have_paise, needed_paise)

        wallet.balance_cents = max(0, have_cents - debit_cents)
        wallet.balance_inr_paise = max(0, have_paise - debit_paise)
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=-debit_cents,
                amount_inr_paise=-debit_paise,
                kind=kind,
                reference_id=reference_id,
                created_at=_utcnow(),
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return {"ok": True, "duplicate": True, "amountCents": 0, "amountInrPaise": 0}
        return {"ok": True, "amountCents": debit_cents, "amountInrPaise": debit_paise}


async def bill_pstn_call_if_applicable(call_id: str) -> None:
    await bill_call_usage_if_applicable(call_id)


def _resolve_call_wallet_debit(
    *,
    call_id: str,
    channel: str,
    duration_sec: int,
    settings: Any,
    stored_rate_cents: int | None = None,
    stored_rate_micros: int | None = None,
    stored_rate_inr_paise: int | None = None,
    stored_fx: float | None = None,
) -> tuple[int, int, str]:
    """Return (usd_cents, inr_paise, billing_mode) for wallet debit.

    Honours locked call snapshot rates so calls are never re-priced if admin rates change.
    """
    # Supplier costs describe platform expenditure. Customer debits always use
    # the selling rate locked when this call started, independently of usage.
    if int(duration_sec) <= 0:
        return 0, 0, "catalog_prorated"

    # New call snapshots preserve both currencies. Charge from the native rate
    # in paise for INR wallets and only round USD at the wallet-cent boundary.
    if (
        (stored_rate_micros is not None and int(stored_rate_micros) > 0)
        or (stored_rate_inr_paise is not None and int(stored_rate_inr_paise) > 0)
    ):
        from decimal import Decimal, ROUND_HALF_UP

        duration = max(1, int(duration_sec))
        fx = Decimal(str(stored_fx if stored_fx is not None and float(stored_fx) > 0 else 95.64))
        micros = (
            int(stored_rate_micros)
            if stored_rate_micros is not None and int(stored_rate_micros) > 0
            else int(stored_rate_cents or 0) * 10_000
        )
        inr_rate_paise = (
            int(stored_rate_inr_paise)
            if stored_rate_inr_paise is not None and int(stored_rate_inr_paise) > 0
            else int(
                (Decimal(micros) * fx / Decimal(10_000)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        )
        cents = max(
            1,
            int(
                (Decimal(duration) * Decimal(micros) / Decimal(600_000)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            ),
        )
        paise = max(
            1,
            int(
                (Decimal(duration) * Decimal(inr_rate_paise) / Decimal(60)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            ),
        )
        return cents, paise, "catalog_prorated"

    minutes = max(0.0, float(duration_sec)) / 60.0
    if minutes <= 0:
        minutes = 1.0 / 60.0

    if stored_rate_cents is not None and int(stored_rate_cents) > 0:
        rate_cents = int(stored_rate_cents)
        fx = float(stored_fx if stored_fx is not None and float(stored_fx) > 0 else 95.64)
    elif hasattr(settings, "pstn_rate_usd_cents_per_min"):
        rate_cents = int(
            settings.pstn_rate_usd_cents_per_min
            if channel == "pstn"
            else getattr(settings, "web_agent_rate_usd_cents_per_min", 7)
        )
        fx = float(getattr(settings, "fx_rate_inr", 0) or 95.64) or 95.64
    else:
        try:
            from server.services.saas.billing_rates import effective_rates

            cur_rates = effective_rates()
            rate_cents = int(
                cur_rates["pstn_rate_usd_cents_per_min"]
                if channel == "pstn"
                else cur_rates["web_agent_rate_usd_cents_per_min"]
            )
            fx = float(cur_rates.get("fx_rate_inr") or 95.64)
        except Exception:
            rate_cents = 9 if channel == "pstn" else 7
            fx = 95.64

    cents = max(1, int(round(minutes * rate_cents)))
    paise = max(1, int(round(cents * fx)))
    return cents, paise, "catalog_prorated"


def wallet_debit_display(
    *,
    amount_cents: int | None,
    amount_inr_paise: int | None,
    wallet_currency: str | None,
    fx_rate_inr: float | int | None,
) -> dict[str, int | float | str]:
    """Roll both recorded debit legs into the wallet's primary currency for display."""
    from decimal import Decimal, ROUND_HALF_UP

    cents = abs(int(amount_cents or 0))
    paise = abs(int(amount_inr_paise or 0))
    try:
        fx = Decimal(str(fx_rate_inr))
    except Exception:
        fx = Decimal("0")
    if not fx.is_finite() or fx <= 0:
        fx = Decimal("95.64")

    if str(wallet_currency or "usd").strip().lower() == "inr":
        converted_paise = int((Decimal(cents) * fx).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total_minor = paise + converted_paise
        currency = "INR"
    else:
        converted_cents = int((Decimal(paise) / fx).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        total_minor = cents + converted_cents
        currency = "USD"
    return {"amount": total_minor / 100.0, "currency": currency}


async def bill_call_usage_if_applicable(call_id: str) -> None:
    """Idempotent usage debit after any billed voice session ends."""
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return
    from server.call.call_store import call_store

    stored = await call_store.get(call_id)
    if not stored:
        return
    channel = str(stored.get("channel") or "")
    if channel not in {"pstn", "browser"}:
        return
    tenant_raw = stored.get("tenant_id")
    if not tenant_raw:
        return
    try:
        tenant_id = uuid.UUID(str(tenant_raw))
    except ValueError:
        return
    billed_user = None
    try:
        from server.call.call_ledger import call_ledger

        meta = call_ledger.review_fields(call_id) or {}
        billed_user = _parse_user_id(meta.get("billed_user_id") or stored.get("billed_user_id"))
    except Exception:
        billed_user = _parse_user_id(stored.get("billed_user_id"))

    if billed_user is None and stored.get("session_id", "").startswith("web-agent-"):
        import re
        m = re.search(r"web-agent-([0-9a-fA-F-]{36})-", stored.get("session_id", ""))
        if m:
            billed_user = _parse_user_id(m.group(1))

    duration_sec = int(stored.get("duration_sec") or 0)
    if duration_sec <= 0:
        logger.info("[WALLET] skipping 0-duration voice session debit call=%s channel=%s", call_id, channel)
        return
    # A browser practice run is still billable when it is attributed to a user —
    # that is the existing contract — but it is not a real conversation, so it is
    # tagged distinctly in the ledger and never mixed into PSTN usage reporting.
    kind = "usage_pstn" if channel == "pstn" else ("usage_web_test" if stored.get("is_test") else "usage_web")
    ref = f"call:{call_id}"
    cents, paise, billing_mode = _resolve_call_wallet_debit(
        call_id=call_id,
        channel=channel,
        duration_sec=duration_sec,
        settings=settings,
        stored_rate_cents=stored.get("applied_rate_usd_cents_per_min"),
        stored_rate_micros=stored.get("applied_rate_usd_micros_per_min"),
        stored_rate_inr_paise=stored.get("applied_rate_inr_paise_per_min"),
        stored_fx=stored.get("applied_fx_rate_inr"),
    )
    try:
        await debit_wallet(
            tenant_id,
            kind=kind,
            reference_id=ref,
            user_id=billed_user,
            amount_cents=cents,
            amount_inr_paise=paise,
            fx_rate_inr_override=stored.get("applied_fx_rate_inr"),
            allow_partial=True,
        )
    except Exception as exc:
        logger.warning("[WALLET] bill failed call=%s err=%s", call_id, str(exc)[:160])
        return
    logger.info(
        "[WALLET] billed %s call=%s tenant=%s mode=%s paise=%s",
        kind,
        call_id,
        tenant_id,
        billing_mode,
        paise,
    )


async def debit_did_purchase_in_session(
    session,
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    purchase_id: uuid.UUID,
) -> dict:
    """Charge the monthly number rental.

    A number is bought either from the USD credit or the INR credit, whichever the
    workspace actually holds — the price is the same in both, so a tenant funded in
    one currency is never locked out by the other's empty balance. The caller owns
    the transaction so the purchase/reservation and debit can commit atomically.
    """
    from server.services.saas.billing_rates import load_current_rates

    # The admin-configured rate, not the env default — otherwise a price change
    # in the admin panel changes what the console quotes but not what it charges.
    rates = await load_current_rates()
    want_cents = int(rates["did_monthly_usd_cents"])
    want_paise = int(rates["did_monthly_inr_paise"])
    ref = f"did:{purchase_id}"
    dup = await session.execute(
        select(BillingWalletTransaction).where(
            BillingWalletTransaction.tenant_id == tenant_id,
            BillingWalletTransaction.reference_id == ref,
        )
    )
    if dup.scalar_one_or_none():
        return {"ok": True, "duplicate": True, "amountCents": 0, "amountInrPaise": 0}
    wallet = await session.get(BillingWallet, tenant_id, with_for_update=True)
    if wallet is None:
        wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
        session.add(wallet)
        await session.flush()

    have_cents = int(wallet.balance_cents or 0)
    have_paise = int(wallet.balance_inr_paise or 0)
    # Prefer the wallet's own primary currency, then whichever leg can cover it.
    primary = (wallet.currency or "usd").lower()
    if primary == "inr" and have_paise >= want_paise:
        take_cents, take_paise = 0, want_paise
    elif have_cents >= want_cents:
        take_cents, take_paise = want_cents, 0
    elif have_paise >= want_paise:
        take_cents, take_paise = 0, want_paise
    else:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "insufficient_balance",
                    "message": (
                        "Add funds to your wallet before buying a phone number. "
                        f"A number costs ${want_cents / 100:.2f} per month."
                    ),
                }
            },
        )

    wallet.balance_cents = have_cents - take_cents
    wallet.balance_inr_paise = have_paise - take_paise
    if take_paise and not take_cents:
        wallet.currency = "inr"
    elif take_cents and not take_paise:
        wallet.currency = "usd"
    wallet.updated_at = _utcnow()
    session.add(
        BillingWalletTransaction(
            tenant_id=tenant_id,
            user_id=user_id,
            amount_cents=-take_cents,
            amount_inr_paise=-take_paise,
            kind="did_purchase",
            reference_id=ref,
            created_at=_utcnow(),
        )
    )
    return {"ok": True, "amountCents": take_cents, "amountInrPaise": take_paise}


async def debit_did_purchase(
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    e164: str,
    purchase_id: uuid.UUID,
) -> dict:
    """Charge a DID in its own transaction for callers outside purchase creation."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        result = await debit_did_purchase_in_session(
            session,
            tenant_id,
            user_id=user_id,
            purchase_id=purchase_id,
        )
        await session.commit()
        return result


async def refund_did_purchase(
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    purchase_id: uuid.UUID,
) -> dict[str, Any]:
    """Reverse exactly what a number purchase took.

    The purchase debits a single currency leg (whichever the workspace was funded
    in), so the refund must credit that same leg. Crediting both would mint money
    that was never collected. The original ledger row is therefore the source of
    truth, not the current price — a price change between purchase and refund must
    not alter what is returned.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    ref = f"did:{purchase_id}"
    async with factory() as session:
        original = (
            await session.execute(
                select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == ref)
            )
        ).scalar_one_or_none()
        if original is None:
            logger.warning("[WALLET] refund skipped: no debit found for %s", ref)
            return {"ok": False, "reason": "no_original_debit"}

        refund_ref = f"did_refund:{purchase_id}"
        dup = (
            await session.execute(
                select(BillingWalletTransaction).where(
                    BillingWalletTransaction.reference_id == refund_ref
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return {"ok": True, "duplicate": True}

        # Reverse the signs of whatever was actually debited.
        back_cents = abs(int(original.amount_cents or 0))
        back_paise = abs(int(original.amount_inr_paise or 0))
        wallet = await session.get(BillingWallet, tenant_id, with_for_update=True)
        if wallet is None:
            wallet = BillingWallet(
                tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow()
            )
            session.add(wallet)
            await session.flush()
        wallet.balance_cents = int(wallet.balance_cents or 0) + back_cents
        wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + back_paise
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id or original.user_id,
                amount_cents=back_cents,
                amount_inr_paise=back_paise,
                kind="did_refund",
                reference_id=refund_ref,
                created_at=_utcnow(),
            )
        )
        await session.commit()
    logger.info(
        "[WALLET] refunded did purchase=%s cents=%s paise=%s",
        purchase_id,
        back_cents,
        back_paise,
    )
    return {"ok": True, "amountCents": back_cents, "amountInrPaise": back_paise}


async def create_topup_checkout(tenant_id: uuid.UUID, amount_usd: float, email: str) -> dict:
    """Card checkout via Stripe has been permanently removed. Use Razorpay order creation instead."""
    raise ValueError("stripe_removed")


async def credit_topup_from_session(tenant_id: uuid.UUID, session_id: str, amount_cents: int) -> None:
    """Stripe webhook credit has been permanently removed."""
    raise ValueError("stripe_removed")
