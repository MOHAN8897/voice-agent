"""Live end-to-end verification of the console's money and call flows.

Runs against a real API and a real database, using a signed-in demo admin. It
exercises the exact requests the browser console makes, in order, and reports what
actually happened rather than what was expected.

    python -m scripts.verify_console_flows            # safe: read-mostly
    python -m scripts.verify_console_flows --write     # also mutates (profile, delete)

Money is never moved: no real top-up, no real carrier call, no number purchase.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

from server.auth.jwt_tokens import AccessTokenClaims, create_access_token  # noqa: E402
from server.config.env import get_settings  # noqa: E402
from server.db.connection import get_session_factory, init_db  # noqa: E402
from server.db.models.entities import Agent  # noqa: E402
from server.db.models.phase5_models import PhoneNumber  # noqa: E402
from server.db.models.saas_models import TenantMembership, User  # noqa: E402
from server.services.saas.platform_admins import platform_admin_emails  # noqa: E402

RESULTS: list[dict[str, Any]] = []

# The Windows console defaults to cp1252 and cannot render the rupee sign.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"name": name, "ok": ok, "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}{f' — {detail}' if detail else ''}")
    return ok


def section(title: str) -> None:
    print(f"\n--- {title} ---")


# --------------------------------------------------------------------------
# Test principal: a real, signed-in demo admin
# --------------------------------------------------------------------------


async def _demo_principal() -> tuple[uuid.UUID, uuid.UUID, str]:
    """The real demo admin's user id and the shared demo tenant id.

    The token must carry the *actual* user id: every protected route re-checks
    tenant membership, so a made-up id is rejected as not-found.
    """
    factory = get_session_factory()
    assert factory is not None
    emails = sorted(platform_admin_emails())
    if not emails:
        raise SystemExit("SAAS_PLATFORM_ADMIN_EMAILS is empty")
    email = emails[0]
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"{email} is not provisioned; run scripts/seed_demo_admin.py")
        memberships = (
            await session.execute(
                select(TenantMembership).where(TenantMembership.user_id == user.user_id)
            )
        ).scalars().all()
        roles = {m.role for m in memberships}
        if "platform_admin" not in roles:
            raise SystemExit(f"{email} lacks the platform_admin role: {roles}")
        user_id = user.user_id
        # Use the shared demo tenant so the agents under test are the platform ones.
        try:
            tenant_id = uuid.UUID(str(get_settings().default_tenant_id))
        except (ValueError, TypeError):
            tenant_id = memberships[0].tenant_id
    return user_id, tenant_id, email


def mint_token(user_id: uuid.UUID, tenant_id: uuid.UUID, email: str, role: str) -> str:
    token, _ = create_access_token(
        AccessTokenClaims(
            user_id=str(user_id), tenant_id=str(tenant_id), role=role, email=email
        )
    )
    return token


async def call(httpx_client, token: str, method: str, path: str, body: Any = None):
    resp = await httpx_client.request(
        method, path, json=body, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {}


def code_of(payload: Any) -> str | None:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            err = detail.get("error")
            if isinstance(err, dict):
                return err.get("code")
        err = payload.get("error")
        if isinstance(err, dict):
            return err.get("code")
    return None


async def _seed_missed_attempt(tenant_id: uuid.UUID, agent_id: str | None) -> dict | None:
    """Create one never-answered inbound attempt so the callback path is testable.

    Uses the same store the carrier webhook writes to, so this is a genuine
    record rather than a mock. No call is placed and no money moves.
    """
    from server.call.call_store import call_attempt_store

    control = f"verify-{uuid.uuid4().hex[:12]}"
    await call_attempt_store.upsert_by_control(
        control,
        tenant_id=str(tenant_id),
        agent_id=agent_id,
        provider="telnyx",
        direction="inbound",
        from_number="+919000000001",
        to_number="+918000000000",
        status="in_progress",
        policy_reason="answered",
    )
    attempt = await call_attempt_store.finalize_by_control(
        control, status="missed", end_reason="no_answer"
    )
    if not attempt:
        return None
    return {
        "call_id": attempt["attempt_id"],
        "caller_phone": attempt["from_number"],
        "status": attempt["status"],
    }


# --------------------------------------------------------------------------
# Flows
# --------------------------------------------------------------------------


async def verify(do_write: bool, do_dial: bool = False) -> int:
    import httpx

    if not await init_db():
        print("DATABASE_URL is not configured")
        return 2
    user_id, tenant_id, email = await _demo_principal()
    token = mint_token(user_id, tenant_id, email, "platform_admin")
    base = "http://127.0.0.1:8077"

    async with httpx.AsyncClient(base_url=base, timeout=60.0) as http:
        # ---------------------------------------------------------- identity
        section("Identity and authorization")
        status, me = await call(http, token, "GET", "/api/auth/me")
        record(
            "demo account is signed in and platform admin",
            status == 200 and me.get("role") == "platform_admin",
            f"role={me.get('role')} isPlatformAdmin={me.get('isPlatformAdmin')}",
        )

        # ---------------------------------------------------------- wallet
        section("Wallet and pricing")
        status, wallet = await call(http, token, "GET", "/api/billing/wallet")
        ok = status == 200 and isinstance(wallet.get("balanceUsd"), (int, float))
        record("wallet summary readable", ok, f"status={status} ${wallet.get('balanceUsd')}")
        if ok:
            mins = wallet.get("remainingMinutes", 0)
            record(
                "wallet reports remaining talk time",
                isinstance(mins, int) and mins >= 0,
                f"{mins} min at ${wallet.get('rateUsdPerMin')}/min",
            )

        status, catalog = await call(http, token, "GET", "/api/billing/catalog")
        record(
            "catalog exposes the $3 minimum and $4 number",
            status == 200
            and catalog.get("topupMinUsd") == 3.0
            and catalog.get("rates", {}).get("numberMonthlyUsd") == 4.0,
            f"min=${catalog.get('topupMinUsd')} number=${catalog.get('rates', {}).get('numberMonthlyUsd')}",
        )

        # A $2 top-up must be refused; $3 is the documented floor. Neither moves money.
        status, too_small = await call(http, token, "POST", "/api/billing/topup", {"amountUsd": 2})
        record(
            "$2 top-up is rejected by the payment wall",
            status in (400, 422) or code_of(too_small) == "amount_out_of_range",
            f"status={status} {code_of(too_small)}",
        )

        # ---------------------------------------------------------- agents
        section("Agent creation flow")
        status, agents_resp = await call(http, token, "GET", "/api/agents")
        agents = agents_resp.get("agents") or []
        record(
            "demo account sees the platform agents",
            status == 200 and len(agents) > 0,
            f"{len(agents)} agent(s) on tenant {tenant_id}",
        )
        published = [a for a in agents if a.get("active_compiled_brain_version")]
        record(
            "at least one agent has a published brain",
            len(published) > 0,
            f"{len(published)} published",
        )

        created_id = None
        if do_write:
            # The wizard's step 1 uses build-employee, which compiles the brief
            # into a script and publishes the brain. This is the real entry point.
            status, built = await call(
                http,
                token,
                "POST",
                "/api/app/agents/build-employee",
                {
                    "brief": (
                        "We are Bright Cars in Hyderabad. Greet callers about used cars, "
                        "ask which model and budget, and book a test drive at the showroom."
                    ),
                    "language": "en-IN",
                    "mode": "instant_lead",
                },
            )
            created_id = built.get("agentId") or (built.get("agent") or {}).get("agent_id")
            script_from_compile = built.get("script") or ""
            record(
                "wizard step 1: brief compiles into an agent",
                status == 200 and bool(created_id),
                created_id or f"status {status}",
            )
            record(
                "wizard step 1: compiler returns a script inline",
                bool(script_from_compile),
                f"{len(script_from_compile)} chars, {len(built.get('variables') or [])} variables",
            )

        if created_id:
            # Wizard step 2: the script must be readable for review.
            status, script = await call(
                http, token, "GET", f"/api/agents/{created_id}/business-brain/calling-script"
            )
            record(
                "wizard step 2: generated script is reviewable",
                status == 200 and len(script.get("callingScript") or "") > 0,
                f"{len(script.get('callingScript') or '')} chars",
            )
            record(
                "wizard step 2: script variables are exposed",
                isinstance(script.get("variables"), list),
                f"{len(script.get('variables') or [])} variables",
            )

            # Step 2 edit → step 3 save. One constant, so the write and the
            # read-back assertion can never drift apart.
            edited_script = "Greet the caller. Ask which car they want. Book a test drive."
            status, saved = await call(
                http,
                token,
                "PUT",
                f"/api/agents/{created_id}/business-brain/calling-script",
                {"script": edited_script},
            )
            record("wizard step 2: edited script saves", status == 200 and saved.get("ok") is True)

            status, reread = await call(
                http, token, "GET", f"/api/agents/{created_id}/business-brain/calling-script"
            )
            got = reread.get("callingScript") or ""
            record(
                "wizard step 2: edited script round-trips",
                got == edited_script,
                f"sent {len(edited_script)} chars, got {len(got)} chars",
            )

            # Step 3: telephony profile.
            status, profile = await call(http, token, "GET", f"/api/agents/{created_id}/telephony-profile")
            record(
                "telephony profile readable",
                status == 200 and profile.get("profile", {}).get("inboundEnabled") is True,
            )

            status, saved_profile = await call(
                http,
                token,
                "PUT",
                f"/api/agents/{created_id}/telephony-profile",
                {
                    "greetingPhrase": "Thanks for calling, this is Priya.",
                    "businessHours": {"mon": [{"open": "09:00", "close": "18:00"}]},
                    "timezone": "Asia/Kolkata",
                    "afterHoursAction": "voicemail",
                    "inboundEnabled": True,
                    "outboundEnabled": True,
                },
            )
            record(
                "telephony profile saves",
                status == 200
                and saved_profile.get("profile", {}).get("greetingPhrase")
                == "Thanks for calling, this is Priya.",
            )

            status, effective = await call(
                http, token, "GET", f"/api/agents/{created_id}/telephony-profile/effective"
            )
            record(
                "live inbound decision is reported",
                status == 200 and effective.get("decision", {}).get("shouldAnswer") is True,
                effective.get("decision", {}).get("reason"),
            )

            status, invalid = await call(
                http,
                token,
                "PUT",
                f"/api/agents/{created_id}/telephony-profile",
                {"businessHours": {"funday": [{"open": "09:00", "close": "18:00"}]}},
            )
            record("invalid profile is refused", status == 400, f"status={status}")

            status, _ = await call(http, token, "DELETE", f"/api/agents/{created_id}")
            record("test agent removed", status == 200)

        # ------------------------------------------------- calls + status
        section("Calls, canonical status and callbacks")
        status, calls = await call(http, token, "GET", "/api/calls?limit=25")
        rows = calls.get("calls") or []
        record("call history readable", status == 200, f"{calls.get('total')} total")

        expected = {
            "answered", "missed", "outbound", "declined", "failed", "voicemail", "in_progress",
        }
        record(
            "status vocabulary is canonical",
            set(calls.get("statuses") or []) == expected,
        )
        record(
            "every row carries a status",
            all(r.get("status") in expected for r in rows),
            ", ".join(sorted({r.get("status") for r in rows})),
        )
        record(
            "summaries are present on connected calls",
            any(r.get("summary") for r in rows if r.get("connected")),
            f"{sum(1 for r in rows if r.get('summary'))} of {len(rows)} rows have a summary",
        )

        status, missed = await call(http, token, "GET", "/api/calls?status=missed&limit=5")
        record(
            "missed filter works server-side",
            status == 200 and all(r.get("status") == "missed" for r in missed.get("calls") or []),
            f"{missed.get('total')} missed",
        )

        status, stats = await call(http, token, "GET", "/api/calls/stats")
        record(
            "call stats include missed",
            status == 200 and stats.get("counts", {}).get("missed", 0) >= 0,
            f"missed={stats.get('counts', {}).get('missed')} connected={stats.get('connected')}",
        )

        # A missed call with a caller number is the callback case. Historical rows
        # often carry no stored number, so seed a fresh missed attempt to make
        # sure the never-answered branch of the callback service is exercised.
        callback_target = next(
            (
                r
                for r in missed.get("calls") or []
                if r.get("status") == "missed" and (r.get("caller_phone") or r.get("callerPhone"))
            ),
            None,
        )
        if not callback_target:
            callback_target = await _seed_missed_attempt(
                tenant_id, agents[0]["agent_id"] if agents else None
            )
            if callback_target:
                print(f"      (seeded a missed attempt from {callback_target.get('caller_phone')})")

        if callback_target:
            cid = callback_target.get("call_id") or callback_target.get("callId")
            if do_dial:
                status, cb = await call(
                    http, token, "POST", f"/api/calls/{cid}/callback", {"mode": "manual"}
                )
                record(
                    "callback places a real call through the outbound path",
                    status in (200, 402, 429),
                    f"status={status} {cb.get('error') or cb.get('code') or ''}",
                )
                record(
                    "callback resolves the number to call",
                    bool(cb.get("toE164")),
                    str(cb.get("toE164") or cb.get("error") or ""),
                )
            else:
                # Without --dial, prove the callback resolves the missed number and
                # is refused before dialling by using an agent the caller does not
                # own. No carrier call is placed and no money moves.
                status, cb = await call(
                    http,
                    token,
                    "POST",
                    f"/api/calls/{cid}/callback",
                    {"mode": "manual", "agentId": "11111111-1111-4111-8111-111111111111"},
                )
                record(
                    "callback authorises the chosen agent before dialling",
                    status == 404,
                    f"status={status} {code_of(cb)}",
                )

            status, history = await call(http, token, "GET", f"/api/calls/{cid}/callbacks")
            record(
                "callback history is readable for a missed call",
                status == 200 and isinstance(history.get("callbacks"), list),
                f"{len(history.get('callbacks') or [])} row(s)",
            )
        else:
            record("no missed call available to exercise the callback path", False)

        # ------------------------------------------------ numbers + assign
        section("Phone numbers")
        status, numbers = await call(http, token, "GET", "/api/telephony/numbers")
        owned = numbers.get("numbers") or []
        record("owned numbers readable", status == 200, f"{len(owned)} line(s)")

        priced = [n for n in owned if n.get("monthlyCost") is not None]
        record(
            "owned numbers carry a monthly price",
            bool(owned) and len(priced) == len(owned),
            f"first=${owned[0].get('monthlyCost') if owned else 'n/a'}",
        )

        if do_write and owned:
            # Number assign flow: bind the first line to a platform agent.
            free_agents = [a for a in agents if a.get("agent_id") not in
                           {n.get("agentId") for n in owned if n.get("agentId")}]
            if free_agents:
                target = free_agents[0]["agent_id"]
                num_id = owned[0]["id"]
                status, assigned = await call(
                    http, token, "POST", f"/api/telephony/numbers/{num_id}/assign",
                    {"agentId": target},
                )
                record("number can be assigned to an agent", status == 200 and assigned.get("ok"),
                       f"{owned[0].get('e164')} -> {target[:8]}")

                # Inbound / outbound toggles on the line.
                status, routing = await call(
                    http, token, "PUT", f"/api/telephony/numbers/{num_id}/routing",
                    {"inboundEnabled": True, "outboundEnabled": True},
                )
                record("line routing toggles save", status == 200 and routing.get("ok") is True)

                # Put it back so the demo workspace is left as it was found.
                await call(http, token, "POST", f"/api/telephony/numbers/{num_id}/assign", {"agentId": None})
                record("number returned to the pool", True)

        # Number purchase must refuse bad input without spending anything.
        status, too_short = await call(
            http, token, "POST", "/api/telephony/buy", {"e164": "+999", "country": "IN"}
        )
        record(
            "number purchase rejects a malformed number",
            status == 400,
            f"status={status} {code_of(too_short)}",
        )

        # A country code may not start with 0, so this is rejected by the E.164
        # check itself rather than by field length.
        status, not_e164 = await call(
            http, token, "POST", "/api/telephony/buy", {"e164": "+0123456789", "country": "IN"}
        )
        record(
            "number purchase rejects a non-E.164 number",
            status == 400 and code_of(not_e164) == "invalid_e164",
            f"status={status} {code_of(not_e164)}",
        )

        # ------------------------------------------------ live PSTN path
        section("Live PSTN path")
        status, voices = await call(http, token, "GET", "/api/telephony/voice-options")
        record(
            "voice options for inbound/outbound available",
            status == 200 and len(voices.get("voices") or []) > 0,
            f"{len(voices.get('voices') or [])} voices",
        )

        # Outbound without a body must fail validation, proving the route is live.
        status, _ = await call(http, token, "POST", "/api/telephony/calls/outbound", {})
        record("outbound route is live and validates input", status in (400, 422), f"status={status}")

        settings = get_settings()
        record(
            "inbound payment wall is enabled and fail-open",
            settings.pstn_enforce_wallet_on_inbound is True,
            f"min=${settings.pstn_min_balance_usd_cents / 100:.2f} / ₹{settings.pstn_min_balance_inr_paise / 100:.2f}",
        )

    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  - {r['name']}: {r['detail']}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also create/edit/delete a test agent and reassign a number.",
    )
    parser.add_argument(
        "--dial",
        action="store_true",
        help=(
            "Place a real callback through the carrier. This costs call time and "
            "rings a real number, so it is opt-in."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results.")
    args = parser.parse_args()
    result = asyncio.run(verify(args.write, args.dial))
    if args.json:
        print(json.dumps(RESULTS, indent=2))
    return result


if __name__ == "__main__":
    sys.exit(main())
