"""The platform's Vobiz call capacity: read limits, price bundles, and buy them.

What Vobiz documents (2026-10):

* ``GET /api/v1/Account/{auth_id}/concurrency`` returns ``concurrent_calls``,
  ``max_concurrent`` (= ``base_concurrent_calls_limit`` + ``purchased_concurrent_calls``)
  and ``utilization_pct`` for the account the Auth ID names.
  https://www.vobiz.ai/docs/account/concurrency.md
* The Account object carries ``cps_limit`` (= ``base_cps_limit`` +
  ``purchased_cps``) next to the concurrency fields.
  https://www.vobiz.ai/docs/account/account-object.md
* ``GET /api/v1/accounts/{auth_id}/channel-pricing-preview?resource_type=concurrent_calls|cps&quantity=N``
  prices extra capacity without buying it (``monthly_cost`` as a decimal string,
  ``currency`` from the account's pricing tier).
  https://www.vobiz.ai/docs/account/channel-pricing-preview.md
* ``POST /api/v1/accounts/{auth_id}/channel-subscriptions`` buys capacity; it
  debits the Vobiz balance at once and renews every 30 days. Vobiz: preview and
  confirm first, and never retry a timed-out purchase automatically.
  https://www.vobiz.ai/docs/account/channel-subscriptions.md
* Sub-accounts expose only ``name`` / ``enabled``; there is no documented
  per-sub-account concurrency limit. https://www.vobiz.ai/docs/sub-accounts.md
  Exceeding the account limit fails the call with 429 / SIP 503
  (https://www.vobiz.ai/docs/faq.md).

So Vobiz capacity is one pool per (parent) account and per-tenant channel caps
are enforced by this platform at admission (``call_admission.reserve``).

:func:`purchase_capacity` spends real money from the Vobiz balance, so it is
called only from the admin capacity page after the admin saw the live price and
confirmed it, and it is never retried. This module never logs secrets.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

RESOURCE_TYPES = ("concurrent_calls", "cps")


def _client(client: Any | None = None):
    if client is not None:
        return client
    from server.services.vobiz_client import VobizClient

    return VobizClient()


def _vobiz_message(exc: Exception) -> str:
    """Vobiz's own error text (request bodies never carry credentials)."""
    body = getattr(exc, "body", "") or ""
    try:
        data = json.loads(body)
        msg = (data.get("error") or data.get("message") or data.get("detail")) if isinstance(data, dict) else None
        if isinstance(msg, dict):
            msg = msg.get("message")
        if msg:
            return str(msg)[:300]
    except (ValueError, TypeError):
        pass
    return str(body)[:300] or "Vobiz refused the request."


async def fetch_platform_concurrency(client: Any | None = None) -> dict[str, Any]:
    """Current and maximum concurrent calls on the platform Vobiz account."""
    try:
        vobiz = _client(client)
        if not getattr(vobiz, "configured", True):
            return {"available": False, "reason": "vobiz_not_configured"}
        payload = await vobiz._request("GET", f"/Account/{vobiz.auth_id}/concurrency", retry=False)
    except Exception as exc:  # noqa: BLE001 -- informational read, never blocks billing
        logger.info("[VOBIZ_CONCURRENCY] concurrency read unavailable: %s", type(exc).__name__)
        return {"available": False, "reason": "vobiz_unavailable"}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    try:
        return {
            "available": True,
            "maxConcurrent": int(data.get("max_concurrent") or 0),
            "concurrentCalls": int(data.get("concurrent_calls") or 0),
            "utilizationPct": int(data.get("utilization_pct") or 0),
        }
    except (TypeError, ValueError):
        return {"available": False, "reason": "vobiz_unexpected_response"}


async def fetch_account_limits(client: Any | None = None) -> dict[str, Any]:
    """Concurrency and CPS limits from the Vobiz Account object (base + purchased)."""
    try:
        vobiz = _client(client)
        if not getattr(vobiz, "configured", True):
            return {"available": False, "reason": "vobiz_not_configured"}
        # No trailing slash: "/Account/{id}/" answers 200 with an empty object.
        payload = await vobiz._request("GET", f"/Account/{vobiz.auth_id}", retry=False)
    except Exception as exc:  # noqa: BLE001 -- informational read
        logger.info("[VOBIZ_CONCURRENCY] account read unavailable: %s", type(exc).__name__)
        return {"available": False, "reason": "vobiz_unavailable"}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}

    def num(key: str) -> int | None:
        try:
            return int(data[key]) if data.get(key) is not None else None
        except (TypeError, ValueError):
            return None

    tier = data.get("pricing_tier") if isinstance(data.get("pricing_tier"), dict) else {}
    out = {
        "available": True,
        "concurrentLimit": num("concurrent_calls_limit"),
        "baseConcurrent": num("base_concurrent_calls_limit"),
        "purchasedConcurrent": num("purchased_concurrent_calls"),
        "cpsLimit": num("cps_limit"),
        "baseCps": num("base_cps_limit"),
        "purchasedCps": num("purchased_cps"),
        "currency": str(tier.get("currency") or "") or None,
    }
    if out["concurrentLimit"] is None and out["cpsLimit"] is None:
        return {"available": False, "reason": "vobiz_unexpected_response"}
    return out


async def fetch_balance(client: Any | None = None) -> dict[str, Any]:
    """The Vobiz account balance a purchase is debited from."""
    try:
        vobiz = _client(client)
        if not getattr(vobiz, "configured", True):
            return {"available": False}
        bal = await vobiz.get_balance()
    except Exception as exc:  # noqa: BLE001
        logger.info("[VOBIZ_CONCURRENCY] balance unavailable: %s", type(exc).__name__)
        return {"available": False}
    if not bal.get("ok") or bal.get("fallback"):
        return {"available": False}
    return {"available": True, "balance": str(bal.get("balance")), "currency": bal.get("currency") or "INR"}


async def preview_channel_price(
    quantity: int, client: Any | None = None, *, resource_type: str = "concurrent_calls",
) -> dict[str, Any]:
    """What Vobiz would charge per month for `quantity` more concurrent calls or CPS (no purchase)."""
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("resource_type must be concurrent_calls or cps")
    quantity = int(quantity)
    if quantity < 1 or quantity > 10000:
        raise ValueError("quantity must be between 1 and 10000")
    try:
        vobiz = _client(client)
        payload = await vobiz._request(
            "GET",
            f"/accounts/{vobiz.auth_id}/channel-pricing-preview",
            params={"resource_type": resource_type, "quantity": quantity},
            retry=False,
        )
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status", None)
        logger.info("[VOBIZ_CONCURRENCY] price preview unavailable: %s status=%s", type(exc).__name__, status)
        if status == 400:
            # Vobiz pricing-tier rules (block size, min/max) refused this quantity.
            return {"available": False, "reason": "quantity_not_allowed", "message": _vobiz_message(exc)}
        return {"available": False, "reason": "vobiz_unavailable"}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    try:
        monthly = Decimal(str(data.get("monthly_cost")))
    except (InvalidOperation, TypeError, ValueError):
        return {"available": False, "reason": "vobiz_unexpected_response"}
    if not monthly.is_finite():
        return {"available": False, "reason": "vobiz_unexpected_response"}
    return {
        "available": True,
        "resourceType": resource_type,
        "quantity": quantity,
        "monthlyCost": str(monthly),
        "currency": str(data.get("currency") or ""),
        "periodDays": 30,
    }


async def purchase_capacity(resource_type: str, quantity: int, client: Any | None = None) -> dict[str, Any]:
    """Buy `quantity` concurrent calls or CPS on the platform Vobiz account. Never retried.

    Returns ``{"status": "succeeded", ...}``; ``{"status": "failed", "message"}``
    when Vobiz answered with an error (nothing bought); or ``{"status": "unknown"}``
    when no answer came back (it may have been bought: check before retrying).
    """
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("resource_type must be concurrent_calls or cps")
    quantity = int(quantity)
    if quantity < 1 or quantity > 10000:
        raise ValueError("quantity must be between 1 and 10000")
    vobiz = _client(client)
    if not getattr(vobiz, "configured", True):
        return {"status": "failed", "message": "Vobiz credentials are not configured."}
    try:
        payload = await vobiz._request(
            "POST", f"/accounts/{vobiz.auth_id}/channel-subscriptions",
            json={"resource_type": resource_type, "quantity": quantity}, retry=False,
        )
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status", None)
        logger.warning("[VOBIZ_CONCURRENCY] purchase %s x%s failed: %s status=%s",
                       resource_type, quantity, type(exc).__name__, status)
        if isinstance(status, int) and 400 <= status < 500 and status != 408:
            return {"status": "failed", "httpStatus": status, "message": _vobiz_message(exc)}
        return {"status": "unknown",
                "message": "Vobiz did not answer, so it may or may not have been bought. Check the Vobiz limits "
                           "and balance on this page before trying again."}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    return {
        "status": "succeeded",
        "subscriptionId": str(data.get("id") or "") or None,
        "monthlyCost": str(data.get("monthly_cost") or "") or None,
        "currency": str(data.get("currency") or "") or None,
        "nextBillingDate": str(data.get("next_billing_date") or "") or None,
    }
