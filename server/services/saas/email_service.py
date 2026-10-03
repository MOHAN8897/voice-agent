"""Transactional email via Resend.

The forgot-password / verification mails used to fail *silently*: `send_email`
returned a bare bool that no caller checked, so an unverified sending domain
(Resend answers `403 ... domain is not verified`) turned into an HTTP 200 to the
caller and a reset link that was never delivered.

Everything here therefore reports a structured reason instead of a bare bool, and
`email_provider_status()` exposes whether the deployment can deliver at all so a
route can fail loudly (and non-enumeratingly) rather than pretend it succeeded.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from server.config.env import get_settings

logger = logging.getLogger(__name__)

RESEND_BASE = "https://api.resend.com"

# Resend's own sandbox sender. It only delivers to the account owner's address, so
# it is a last-resort fallback for a single mailbox — never a platform default.
RESEND_SANDBOX_SENDER = "Voxly <onboarding@resend.dev>"


@dataclass(frozen=True)
class EmailResult:
    """Outcome of one send, with a machine-readable reason."""

    ok: bool
    code: str
    detail: str = ""
    provider_status: int | None = None
    provider_message: str = ""
    from_address: str = ""

    def __bool__(self) -> bool:  # `if await send_email(...)` keeps working
        return self.ok


@dataclass
class _ProviderCache:
    expires_at: float = 0.0
    value: dict = field(default_factory=dict)


_status_cache = _ProviderCache()
_STATUS_TTL_SECONDS = 300.0


def _sender_domain(from_address: str) -> str:
    _, _, domain = from_address.partition("@")
    domain = domain.strip().rstrip(">").strip()
    if ">" in domain:  # "Name <a@b.c>" style leftovers
        domain = domain.rsplit("<", 1)[-1]
    return domain.lower()


async def _verified_domains(api_key: str) -> tuple[set[str] | None, str]:
    """Verified sending domains per Resend. `None` means "could not tell"."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{RESEND_BASE}/domains",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code >= 400:
            return None, f"domains_probe_http_{resp.status_code}"
        payload = resp.json()
    except Exception as exc:  # network / TLS / malformed JSON
        return None, f"domains_probe_failed:{type(exc).__name__}"

    names: set[str] = set()
    for row in payload.get("data") or []:
        name = str(row.get("name") or "").strip().lower()
        # A domain that was merely *added* is not usable: until the DKIM/SPF records are
        # published its status stays "not_started" and every send is rejected 403.
        # Counting it as verified here is precisely the silent failure this module
        # exists to remove.
        if name and str(row.get("status") or "").strip().lower() in {"verified"}:
            names.add(name)
    return names, "ok"


async def email_provider_status(*, refresh: bool = False) -> dict:
    """Can this deployment actually deliver transactional email?

    Non-sensitive booleans only — never the API key or a full address list — so it
    is safe to publish on the health endpoint.
    """
    settings = get_settings()
    api_key = (settings.resend_api_key or "").strip()
    from_address = (settings.resend_from_email or "").strip() or RESEND_SANDBOX_SENDER
    domain = _sender_domain(from_address)

    now = time.monotonic()
    if not refresh and _status_cache.value and _status_cache.expires_at > now:
        return dict(_status_cache.value)

    out: dict = {
        "provider": "resend",
        "configured": bool(api_key),
        "sender": from_address,
        "senderDomain": domain,
        "domainVerified": False,
        "deliverable": False,
        "reason": "not_configured",
    }
    if not api_key:
        out["detail"] = "RESEND_API_KEY is not set"
    else:
        verified, probe = await _verified_domains(api_key)
        if verified is None:
            # Probe failed — do not assert a healthy sender we could not confirm,
            # but do not hard-fail the request either: deliveries may still work.
            out["domainVerified"] = domain in {"resend.dev"}
            out["deliverable"] = out["domainVerified"]
            out["reason"] = "probe_unavailable"
            out["detail"] = probe
        elif domain in verified or _is_subdomain_of_verified(domain, verified):
            out["domainVerified"] = True
            out["deliverable"] = True
            out["reason"] = "ok"
        else:
            out["reason"] = "domain_not_verified"
            out["detail"] = (
                f"{domain} has no verified sending domain in Resend — every send "
                "is rejected with 403 validation_error. Add it at "
                "https://resend.com/domains and publish the DKIM/SPF records."
            )
            logger.error("email provider not deliverable: %s", out["detail"])

    _status_cache.value = dict(out)
    _status_cache.expires_at = time.monotonic() + _STATUS_TTL_SECONDS
    return dict(out)


def _is_subdomain_of_verified(domain: str, verified: set[str]) -> bool:
    return any(domain.endswith(f".{root}") for root in verified)


def last_provider_status() -> dict:
    """Cached status without another network round-trip (health endpoints)."""
    if _status_cache.value:
        return dict(_status_cache.value)
    return {
        "provider": "resend",
        "configured": bool((get_settings().resend_api_key or "").strip()),
        "sender": get_settings().resend_from_email or "",
        "senderDomain": _sender_domain(get_settings().resend_from_email or ""),
        "domainVerified": False,
        "deliverable": False,
        "reason": "not_probed",
    }


async def send_email(to: str, subject: str, html: str) -> EmailResult:
    """Send one message. Never raises — callers get a reason either way."""
    settings = get_settings()
    api_key = (settings.resend_api_key or "").strip()
    from_addr = (settings.resend_from_email or "").strip() or RESEND_SANDBOX_SENDER
    if not api_key:
        logger.warning("Resend not configured; skipping email to %s", to)
        return EmailResult(
            ok=False,
            code="not_configured",
            detail="RESEND_API_KEY is not set",
            from_address=from_addr,
        )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{RESEND_BASE}/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": from_addr, "to": [to], "subject": subject, "html": html},
            )
    except Exception as exc:
        logger.error("Resend transport error for %s: %s", to, exc)
        return EmailResult(
            ok=False,
            code="transport_error",
            detail=f"{type(exc).__name__}: {exc}"[:300],
            from_address=from_addr,
        )

    if resp.status_code >= 400:
        message = ""
        try:
            message = str((resp.json() or {}).get("message") or "")[:400]
        except Exception:
            message = resp.text[:300]
        code = "rejected"
        if resp.status_code == 403 and "not verified" in message.lower():
            code = "domain_not_verified"
            # The 5-minute cache just became wrong; re-probe on the next read so a
            # freshly published DNS record is picked up without a restart.
            _status_cache.expires_at = 0.0
        logger.error("Resend failed %s: %s", resp.status_code, message)
        return EmailResult(
            ok=False,
            code=code,
            detail=message,
            provider_status=resp.status_code,
            provider_message=message,
            from_address=from_addr,
        )
    return EmailResult(ok=True, code="sent", provider_status=resp.status_code, from_address=from_addr)


def _email_shell(*paragraphs: str, cta_label: str | None = None, cta_url: str | None = None) -> str:
    button = ""
    if cta_url:
        label = cta_label or "Continue"
        button = (
            f'<p style="margin:24px 0;">'
            f'<a href="{cta_url}" style="background:#6344E7;color:#ffffff;padding:12px 22px;'
            f'border-radius:10px;text-decoration:none;font-weight:600;display:inline-block;">'
            f"{label}</a></p>"
        )
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:520px;margin:0 auto;color:#1a1726;">'
        f"<h2 style=\"font-size:20px;margin:0 0 12px;\">Voxly</h2>{body}{button}"
        '<p style="color:#6b6880;font-size:12px;margin-top:28px;">'
        "You are receiving this because someone used your Voxly account email.</p>"
        "</div>"
    )


async def send_verification_email(to: str, verify_url: str, otp_code: str | None = None) -> EmailResult:
    if otp_code:
        paragraphs = (
            "Welcome to Voxly.",
            f"Your sign-in code is <b style=\"letter-spacing:4px;\">{otp_code}</b>. "
            "It expires in 15 minutes.",
        )
    else:
        paragraphs = ("Welcome to Voxly.", "Confirm your email to finish setting up your account.")
    html = _email_shell(*paragraphs, cta_label="Verify email", cta_url=verify_url)
    return await send_email(to, "Your Voxly verification code", html)


async def send_password_reset_email(to: str, reset_url: str) -> EmailResult:
    html = _email_shell(
        "We received a request to reset your Voxly password.",
        "This link expires in 1 hour and can be used once.",
        "If you did not request this, you can ignore this email — nothing has changed.",
        cta_label="Reset password",
        cta_url=reset_url,
    )
    return await send_email(to, "Reset your Voxly password", html)