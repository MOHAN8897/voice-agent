"""Read-only view of the platform's Vobiz concurrent-call capacity.

What Vobiz documents (2026-10):

* ``GET /api/v1/Account/{auth_id}/concurrency`` returns ``concurrent_calls``,
  ``max_concurrent`` (= ``base_concurrent_calls_limit`` + ``purchased_concurrent_calls``)
  and ``utilization_pct`` for the account the Auth ID names.
  https://www.vobiz.ai/docs/account/concurrency.md
* ``GET /api/v1/accounts/{auth_id}/channel-pricing-preview?resource_type=concurrent_calls&quantity=N``
  prices extra capacity without buying it (``monthly_cost`` as a decimal string,
  ``currency`` from the account's pricing tier).
  https://www.vobiz.ai/docs/account/channel-pricing-preview.md
* ``POST /api/v1/accounts/{auth_id}/channel-subscriptions`` buys capacity; it
  debits the Vobiz balance at once and renews every 30 days.
  https://www.vobiz.ai/docs/account/channel-subscriptions.md
* Sub-accounts expose only ``name`` / ``enabled``; there is no documented
  per-sub-account concurrency limit. https://www.vobiz.ai/docs/sub-accounts.md
  Exceeding the account limit fails the call with 429 / SIP 503
  (https://www.vobiz.ai/docs/faq.md).

So Vobiz capacity is one pool per (parent) account and per-tenant channel caps
are enforced by this platform at admission (``call_admission.reserve``). This
module deliberately has no purchase call: buying Vobiz capacity spends real money
and is an operator decision made in the Vobiz console. It never logs secrets.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)


def _client(client: Any | None = None):
    if client is not None:
        return client
    from server.services.vobiz_client import VobizClient

    return VobizClient()


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


async def preview_channel_price(quantity: int, client: Any | None = None) -> dict[str, Any]:
    """What Vobiz would charge per month for `quantity` extra concurrent calls (no purchase)."""
    quantity = int(quantity)
    if quantity < 1 or quantity > 10000:
        raise ValueError("quantity must be between 1 and 10000")
    try:
        vobiz = _client(client)
        payload = await vobiz._request(
            "GET",
            f"/accounts/{vobiz.auth_id}/channel-pricing-preview",
            params={"resource_type": "concurrent_calls", "quantity": quantity},
            retry=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("[VOBIZ_CONCURRENCY] price preview unavailable: %s", type(exc).__name__)
        return {"available": False, "reason": "vobiz_unavailable"}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    try:
        monthly = Decimal(str(data.get("monthly_cost")))
    except (InvalidOperation, TypeError, ValueError):
        return {"available": False, "reason": "vobiz_unexpected_response"}
    return {
        "available": True,
        "quantity": quantity,
        "monthlyCost": str(monthly),
        "currency": str(data.get("currency") or ""),
        "periodDays": 30,
    }
