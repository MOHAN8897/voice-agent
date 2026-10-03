"""Tenant-safe projection of a call record.

`GET /api/call/{id}` is a tenant-facing endpoint, but the call body it returns is
built from the internal ledger, so a customer could read their own wholesale carrier
cost, the upstream model's list rate, the resolved provider stack and the PSTN
forensics. Those are not the customer's business: knowing them is enough to compute
the margin being charged on their call and to shop the underlying vendors directly.

So the detail payload is split in two:

  * **Customer metrics** — duration, turns, what they were billed, disposition.
    These are the numbers a tenant legitimately needs to reconcile an invoice.
  * **Internal economics and architecture** — carrier and model unit rates, the
    resolved provider stack, queue/archive bookkeeping, PSTN timing forensics.
    These are for the platform team and stay behind an internal role.

The redaction happens here, on the response, rather than only in the UI: hiding a
field in React still ships it to the browser.
"""
from __future__ import annotations

from typing import Any

# Usage/ledger keys that expose wholesale cost or upstream list rates.
INTERNAL_USAGE_KEYS: frozenset[str] = frozenset(
    {
        # Wholesale carrier economics. Showing these lets a tenant compute margin and
        # bypass us to the same carrier.
        "telnyx_inr",
        "telnyx_usd",
        "telnyx_inr_per_min",
        # Upstream model cost and its published list rate.
        "model_cost_inr",
        "model_cost_usd",
        "model_cost_inr_per_min",
        "gemini_list_audio_inr_per_min",
        # FX is an internal settlement detail.
        "fx_rate_inr",
        "fx_source",
        "transcription_billing",
        "cost_inr",
        "cost_inr_per_min",
    }
)

# Top-level meta keys that are internal architecture, not customer data.
INTERNAL_META_KEYS: frozenset[str] = frozenset(
    {
        "resolved_stack",
        "combination_id",
        "compiled_brain_version",
        "dial_request_id",
        "pstn_forensics",
        "transcript_source",
        "model_cost_inr",
        "telnyx_inr",
        "cost_inr",
        "cost_inr_per_min",
    }
)

# Top-level meta keys that are fine for a tenant: the billed number and the
# aggregate cost are on their invoice.
CUSTOMER_META_KEYS: tuple[str, ...] = (
    "call_id",
    "agent_id",
    "channel",
    "pipeline",
    "direction",
    "caller_id",
    "tier",
    "environment",
    "started_at",
    "ended_at",
    "duration_sec",
    "end_reason",
    "cost_usd",
    "status",
    "finalization_status",
)


def _strip_finalization(finalization: dict[str, Any]) -> dict[str, Any]:
    """Keep "did it archive", drop the names of the workers that did it."""
    keep = ("status", "attempted_at", "error")
    return {k: v for k, v in finalization.items() if k in keep and v not in (None, "")}


def redact_call_detail_for_tenant(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the customer-facing subset of a call detail payload."""
    out: dict[str, Any] = {}
    for key in CUSTOMER_META_KEYS:
        if payload.get(key) is not None:
            out[key] = payload[key]

    usage_in = payload.get("usage") or {}
    usage_out: dict[str, Any] = {}
    for key in ("turns", "input_audio_tokens", "output_audio_tokens", "duration_sec"):
        if usage_in.get(key) is not None:
            usage_out[key] = usage_in[key]
    if usage_out:
        out["usage"] = usage_out

    finalization = payload.get("finalization")
    if isinstance(finalization, dict):
        safe = _strip_finalization(finalization)
        if safe:
            out["finalization"] = safe

    transcript = payload.get("post_call_transcript")
    if isinstance(transcript, dict):
        safe_transcript = {k: transcript.get(k) for k in ("status", "chars", "language") if transcript.get(k) is not None}
        if safe_transcript:
            out["post_call_transcript"] = safe_transcript

    # Tell the UI this is the redacted view so it can label the panel honestly
    # instead of rendering an empty field and looking broken.
    out["internal_fields_hidden"] = True
    return out


def is_internal_viewer(role: str | None) -> bool:
    return (role or "") in {"platform_admin", "administrator", "developer"}