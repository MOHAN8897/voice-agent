"""Call setup against vendor outages: retry once, then fail honestly.

Used by the PSTN dial paths before the carrier is asked to ring anyone. A
vendor failure (Sarvam out of credits, a dead key, a 5xx) gets one more
preparation attempt — by then the key pool has moved to the backup key — and
if that also fails the tenant gets a clear "voice service unavailable, you
weren't charged" answer while the admin panel gets an incident with the
rejected call counted.
"""
from __future__ import annotations

from typing import Any

from server.services import provider_health as ph
from server.utils.logger import logger

VOICE_SERVICE_UNAVAILABLE = "voice_service_unavailable"
VOICE_SERVICE_UNAVAILABLE_MESSAGE = (
    "We couldn't start this call because the voice service is temporarily unavailable. "
    "You weren't charged. Please try again in a few minutes."
)
RETRY_AFTER_S = 120


def setup_failure(exc: BaseException | None) -> ph.ProviderFailure | None:
    """The vendor failure behind a call-setup exception, if there was one."""
    if exc is None:
        return None
    return ph.provider_failure_from(exc)


def should_retry(exc: BaseException) -> bool:
    failure = setup_failure(exc)
    return failure is not None and failure.category != ph.BAD_REQUEST


async def prepare_with_retry(registry: Any, provider: str, external_id: str, meta: dict[str, Any]) -> None:
    """``registry.prepare`` with one retry after a vendor failure."""
    from server.services.pstn_debug import log_pstn

    try:
        await registry.prepare(provider, external_id, meta)
        return
    except Exception as exc:
        failure = setup_failure(exc)
        if failure is None or failure.category == ph.BAD_REQUEST:
            raise
        log_pstn("prewarm.retry", control=external_id, provider=provider,
                 failed_provider=failure.provider, category=failure.category)
        logger.warning("[PSTN] prewarm retry after %s %s failure", failure.provider, failure.category)
    await registry.prepare(provider, external_id, meta)


def unavailable_result(failure: ph.ProviderFailure, *, call_id: str | None, tenant_id: str | None) -> dict[str, Any]:
    """Tenant-facing refusal; also counts the rejected call on the incident."""
    try:
        ph.provider_health.note_call_rejected(
            failure.provider, failure.component, failure.category, call_id=call_id, tenant_id=tenant_id,
        )
    except Exception as err:
        logger.warning("[HEALTH] note_call_rejected failed kind=%s", type(err).__name__)
    return {
        "ok": False,
        "code": VOICE_SERVICE_UNAVAILABLE,
        "error": VOICE_SERVICE_UNAVAILABLE_MESSAGE,
        "status": 503,
        "retry_after": RETRY_AFTER_S,
    }
