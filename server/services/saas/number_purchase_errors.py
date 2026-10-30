"""One place that explains a number-purchase outcome, to the tenant and to the operator.

Every refusal and every provisioning failure is reduced to a stable ``code``.
This module turns that code into:

* tenant copy: plain, respectful, actionable, and explicit about money (charged,
  not charged, refunded). It never names the carrier, never shows a raw error
  code, and never says "the platform's carrier account is out of balance".
* admin copy: the specific platform reason in operator language, what to do
  about it, and where to do it. This is where "Vobiz" and balances belong.

The console shows the tenant ``message`` the API returns, so changing the copy
here changes it everywhere (buy response, purchase status poll, banner).
"""
from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------- tenant copy

_NOT_CHARGED = "You were not charged."

#: Refusals that happen before any money moves (the buy request itself).
TENANT_REFUSAL_MESSAGES: dict[str, str] = {
    "insufficient_balance": "Your wallet doesn't have enough credit for this number. Add credit and try again. You were not charged.",
    "voice_kyc_required": "Please complete phone service verification before buying a number. You were not charged.",
    "voice_verification_unavailable": "We couldn't confirm your verification status just now. Please try again in a few minutes. You were not charged.",
    "kyc_required": "Please verify your identity before buying a number. You were not charged.",
    "verification_required": "Please verify your email address before buying a number. You were not charged.",
    "email_not_verified": "Please verify your email address before buying a number. You were not charged.",
    "number_reserved": "Someone else is buying this number right now. Please choose another number. You were not charged.",
    "number_unavailable": "This number isn't available any more. Please choose another number. You were not charged.",
    "carrier_price_above_retail": "This number isn't available at the moment. Please choose another number. You were not charged.",
    "carrier_balance_exhausted": "We couldn't get this number right now. Your wallet wasn't charged. Please try again later or choose another number.",
    "carrier_not_configured": "Buying numbers is paused for maintenance. Your wallet wasn't charged. Please try again later.",
    "carrier_auth_failed": "Buying numbers is paused for maintenance. Your wallet wasn't charged. Please try again later.",
    "carrier_inventory_unavailable": "We couldn't check this number's availability just now. Your wallet wasn't charged. Please try again in a few minutes.",
    "carrier_order_failed": "We couldn't get this number right now. Your wallet wasn't charged. Please try again later or choose another number.",
    "purchase_temporarily_unavailable": "We couldn't complete your purchase just now. Your wallet wasn't charged. Please try again in a few minutes.",
    "number_limit": "Your workspace has reached its phone number limit. Release a number you no longer need, or contact support to raise the limit. You were not charged.",
    "invalid_e164": "That doesn't look like a valid phone number. Please choose a number from the list. You were not charged.",
    "invalid_agent": "Please choose one of your agents to answer this number, or leave it unassigned. You were not charged.",
    "tenant_not_found": "We couldn't find your workspace. Please sign in again. You were not charged.",
    "stripe_removed": "Card checkout is no longer available. Please pay from your wallet. You were not charged.",
    "stripe_not_configured": "Card checkout is no longer available. Please pay from your wallet. You were not charged.",
    "rate_limited": "Too many purchase attempts. Please wait a minute and try again. You were not charged.",
}

_GENERIC_REFUSAL = "We couldn't complete your purchase just now. Your wallet wasn't charged. Please try again in a few minutes."

#: Failures after the wallet was debited. Keyed by provisioning error code; the
#: refund state decides the money sentence.
_FAILED_REFUNDED: dict[str, str] = {
    "number_taken": "This number was taken just before we could activate it. We've refunded the charge to your wallet. Please choose another number.",
    "voice_kyc_not_approved": "We couldn't activate this number because your phone service verification isn't approved yet. We've refunded the charge to your wallet.",
}
_FAILED_REFUNDED_DEFAULT = "We couldn't activate this number right now, so we've refunded the charge to your wallet. Please try again later or choose another number."
_FAILED_REFUND_PENDING = (
    "We couldn't activate this number. Your refund is being processed and our team has been notified, "
    "so you don't need to do anything. Please don't buy this number again."
)
NEEDS_ATTENTION_MESSAGE = (
    "Your payment is safe. Activating this number is taking longer than usual and our team has been notified. "
    "You don't need to buy it again: we'll finish the setup or refund you."
)
PROVISIONING_MESSAGE = "Payment received. We're activating your number; this usually takes under a minute."
REFUNDED_MESSAGE = "This purchase was cancelled and the charge has been refunded to your wallet."


def tenant_refusal_message(code: str) -> str:
    """Copy for a buy request refused before any debit."""
    return TENANT_REFUSAL_MESSAGES.get(str(code or ""), _GENERIC_REFUSAL)


def tenant_purchase_message(status: str, code: str | None, refunded: bool | None) -> str | None:
    """Copy for the purchase status poll (after the wallet was debited)."""
    status = str(status or "")
    if status in {"active", "provisioned"}:
        return None
    if status == "refunded":
        return REFUNDED_MESSAGE
    if status == "needs_attention":
        return NEEDS_ATTENTION_MESSAGE
    if status == "failed":
        if refunded:
            return _FAILED_REFUNDED.get(str(code or ""), _FAILED_REFUNDED_DEFAULT)
        return _FAILED_REFUND_PENDING
    return PROVISIONING_MESSAGE


# ---------------------------------------------------------------------- admin copy

BILLING_HREF = "/dev/admin/billing"
ENVIRONMENT_HREF = "/dev/environment"
VERIFICATION_HREF = "/dev/admin/verification"

#: scope: "platform" (fix once, affects every tenant), "tenant", or "number".
ADMIN_EXPLANATIONS: dict[str, dict[str, Any]] = {
    "carrier_balance_exhausted": {
        "scope": "platform",
        "severity": "error",
        "title": "Vobiz account balance is too low to buy numbers",
        "detail": "Vobiz debits the setup fee plus the first month from the parent account when a number is bought. The balance cannot cover that, so purchases are refused (before the tenant is charged) or refunded.",
        "action": "Top up the Vobiz parent account, then ask affected tenants to try again.",
        "href": None,
    },
    "carrier_price_above_retail": {
        "scope": "platform",
        "severity": "warning",
        "title": "Number rent is below Vobiz's price for this number",
        "detail": "The tenant pays one month of the platform rent; Vobiz would charge more (setup + monthly). The sale is refused so numbers are never sold at a loss, and such numbers are hidden from the tenant catalog.",
        "action": "Raise “Phone number monthly rent” in Wallet & rates to at least the Vobiz price shown.",
        "href": BILLING_HREF,
    },
    "carrier_not_configured": {
        "scope": "platform",
        "severity": "error",
        "title": "Vobiz credentials are not configured",
        "detail": "VOBIZ_AUTH_ID / VOBIZ_AUTH_TOKEN (or sub-account encryption key) are missing, so no number can be bought.",
        "action": "Set the Vobiz credentials for this environment and restart the API.",
        "href": ENVIRONMENT_HREF,
    },
    "carrier_auth_failed": {
        "scope": "platform",
        "severity": "error",
        "title": "Vobiz rejected our credentials",
        "detail": "Vobiz answered 401/403 to a purchase request. The tenant was refunded.",
        "action": "Check the Vobiz auth ID and token (and that the sub-account is enabled), then retry.",
        "href": ENVIRONMENT_HREF,
    },
    "carrier_inventory_unavailable": {
        "scope": "platform",
        "severity": "warning",
        "title": "Vobiz inventory could not be reached",
        "detail": "The availability check before charging timed out or failed. No tenant was charged.",
        "action": "Usually transient. If it persists, check Vobiz status and network egress from the API.",
        "href": None,
    },
    "carrier_purchase_refused": {
        "scope": "number",
        "severity": "error",
        "title": "Vobiz refused the purchase",
        "detail": "Vobiz returned “failed to purchase number” (HTTP 500) and the number stayed in its inventory. Vobiz documents this as usually a balance debit failure. The tenant was refunded.",
        "action": "Check the Vobiz account balance and the number in the Vobiz console.",
        "href": None,
    },
    "number_taken": {
        "scope": "number",
        "severity": "info",
        "title": "Number was no longer in Vobiz inventory",
        "detail": "Someone else bought it between the tenant's choice and our order (Vobiz 404). The tenant was refunded.",
        "action": "No action needed.",
        "href": None,
    },
    "provider_confirmation_pending": {
        "scope": "number",
        "severity": "warning",
        "title": "Vobiz did not confirm the order",
        "detail": "The order timed out or Vobiz returned a server error, so we cannot tell if the number was bought. The job retries automatically with back-off and reconciles against the account's numbers first.",
        "action": "If it ends in “needs attention”, look the number up in the Vobiz console: if the account owns it, retry provisioning; if not, refund.",
        "href": None,
    },
    "provider_activation_pending": {
        "scope": "number",
        "severity": "warning",
        "title": "Number bought but not yet activated",
        "detail": "Vobiz confirmed the number ID but activation did not finish.",
        "action": "Retry provisioning. Do not refund: the number is on the account.",
        "href": None,
    },
    "provider_number_id_unavailable": {
        "scope": "number",
        "severity": "warning",
        "title": "Vobiz did not return a number ID",
        "detail": "The number was created locally as pending without a carrier ID.",
        "action": "Check the number in the Vobiz console and retry provisioning.",
        "href": None,
    },
    "provider_provision_failed": {
        "scope": "number",
        "severity": "error",
        "title": "Vobiz refused the order",
        "detail": "A definitive refusal from the carrier. The tenant was refunded.",
        "action": "Check the error type below; retrying the same number usually fails the same way.",
        "href": None,
    },
    "voice_kyc_not_approved": {
        "scope": "tenant",
        "severity": "info",
        "title": "Tenant's phone-service KYC was not approved at activation",
        "detail": "KYC was revoked or expired between payment and activation. The tenant was refunded.",
        "action": "Review the tenant's verification.",
        "href": VERIFICATION_HREF,
    },
    "voice_verification_unavailable": {
        "scope": "platform",
        "severity": "warning",
        "title": "Vobiz KYC status could not be read",
        "detail": "The KYC status lookup failed, so purchases were refused before charging.",
        "action": "Usually transient. If it persists, check Vobiz credentials and the sub-account.",
        "href": VERIFICATION_HREF,
    },
    "purchase_provider_unknown": {
        "scope": "number",
        "severity": "error",
        "title": "Purchase has no known carrier",
        "detail": "The paid purchase row has no provider, so the worker will not guess one.",
        "action": "Refund the tenant, or fix the provider column and retry.",
        "href": None,
    },
    "provisioning_stuck": {
        "scope": "number",
        "severity": "warning",
        "title": "Provisioning is taking too long",
        "detail": "The purchase has been in progress for over 15 minutes.",
        "action": "Check the provisioning worker is running, then retry or refund.",
        "href": None,
    },
    "refund_failed": {
        "scope": "number",
        "severity": "error",
        "title": "Refund could not be credited",
        "detail": "Provisioning failed but the wallet refund did not go through. The tenant has paid for nothing.",
        "action": "Use “Refund” here (it is idempotent) or credit the wallet manually.",
        "href": None,
    },
    # Tenant-side refusals that an operator may still want explained.
    "insufficient_balance": {"scope": "tenant", "severity": "info", "title": "Tenant wallet too low", "detail": "The tenant could not cover the first month's rent.", "action": "No action needed.", "href": None},
    "voice_kyc_required": {"scope": "tenant", "severity": "info", "title": "Tenant has not finished phone-service KYC", "detail": "The purchase was refused before charging.", "action": "No action needed unless the tenant is stuck.", "href": VERIFICATION_HREF},
    "number_unavailable": {"scope": "number", "severity": "info", "title": "Number no longer available", "detail": "It was not in Vobiz's unassigned inventory any more, or another workspace owns it.", "action": "No action needed.", "href": None},
    "number_reserved": {"scope": "number", "severity": "info", "title": "Another checkout held the number", "detail": "Another purchase of the same number was in flight.", "action": "No action needed.", "href": None},
    "number_limit": {"scope": "tenant", "severity": "info", "title": "Workspace number limit reached", "detail": "The tenant's max_numbers limit was hit.", "action": "Raise the workspace limit if appropriate.", "href": None},
    "purchase_temporarily_unavailable": {"scope": "platform", "severity": "error", "title": "Unexpected error in the purchase path", "detail": "An unhandled exception; the tenant was not charged.", "action": "Check the API logs around this time.", "href": None},
}

#: Codes that indicate something the platform (not the tenant) must fix.
PLATFORM_CODES = frozenset(code for code, item in ADMIN_EXPLANATIONS.items() if item["scope"] == "platform")


def admin_explanation(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    item = ADMIN_EXPLANATIONS.get(str(code))
    if item is None:
        return {
            "code": str(code),
            "scope": "number",
            "severity": "warning",
            "title": str(code).replace("_", " ").capitalize(),
            "detail": "No operator explanation is recorded for this code.",
            "action": "Check the activity log and API logs.",
            "href": None,
        }
    return {"code": str(code), **item}


class PurchaseRefused(ValueError):
    """A ``ValueError(code)`` that also carries operator-only context.

    ``str(exc)`` stays the stable code, so every existing ``except ValueError``
    keeps working; the context (carrier price, balance, rent) only ever reaches
    the activity log and the admin panel.
    """

    def __init__(self, code: str, **context: Any) -> None:
        super().__init__(code)
        self.code = code
        self.context = {k: v for k, v in context.items() if v is not None}
