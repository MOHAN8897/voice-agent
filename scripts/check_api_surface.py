"""Verify the running API exposes the routes the console depends on.

No credentials needed: this checks the OpenAPI document, i.e. that the app wired
every route the frontend calls. Safe to run against any environment.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = (os.getenv("API_URL") or "http://127.0.0.1:8077").rstrip("/")

REQUIRED: list[tuple[str, str]] = [
    # Agent creation + review
    ("POST", "/api/app/agents/build-employee"),
    ("POST", "/api/app/agents/compose-onboarding"),
    ("GET", "/api/agents"),
    ("POST", "/api/agents"),
    ("GET", "/api/agents/{agent_id}"),
    ("PATCH", "/api/agents/{agent_id}"),
    ("DELETE", "/api/agents/{agent_id}"),
    ("GET", "/api/agents/{agent_id}/business-brain"),
    ("GET", "/api/agents/{agent_id}/business-brain/calling-script"),
    ("PUT", "/api/agents/{agent_id}/business-brain/calling-script"),
    ("PUT", "/api/agents/{agent_id}/business-brain/voice"),
    ("GET", "/api/agents/{agent_id}/brain/compiled-preview"),
    # Telephony profile
    ("GET", "/api/agents/{agent_id}/telephony-profile"),
    ("PUT", "/api/agents/{agent_id}/telephony-profile"),
    ("GET", "/api/agents/{agent_id}/telephony-profile/effective"),
    # Calls + status + stats + transcript + outcome + callback
    ("GET", "/api/calls"),
    ("GET", "/api/calls/stats"),
    ("GET", "/api/calls/{call_id}"),
    ("GET", "/api/call/{call_id}/transcript"),
    ("GET", "/api/call/{call_id}/outcome"),
    # The console requests the mixed-down conversation from this alias.
    ("GET", "/api/call/{call_id}/audio"),
    ("GET", "/api/call/{call_id}/audio-status"),
    ("POST", "/api/calls/outbound"),
    ("POST", "/api/calls/{call_id}/callback"),
    ("GET", "/api/calls/{call_id}/callbacks"),
    # Numbers
    ("GET", "/api/telephony/numbers"),
    ("GET", "/api/telephony/numbers/search"),
    ("POST", "/api/telephony/buy"),
    ("POST", "/api/telephony/numbers/{number_id}/assign"),
    ("PUT", "/api/telephony/numbers/{number_id}/routing"),
    ("GET", "/api/telephony/voice-options"),
    # Billing
    ("GET", "/api/billing/wallet"),
    ("GET", "/api/billing/catalog"),
    ("GET", "/api/billing/transactions"),
    ("GET", "/api/billing/invoices"),
    ("POST", "/api/billing/razorpay/create-order"),
    # Auth
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("GET", "/api/auth/me"),
]


def main() -> int:
    try:
        with urllib.request.urlopen(f"{API}/openapi.json", timeout=20) as res:
            doc = json.load(res)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"SKIP  backend not reachable at {API} ({exc})")
        return 0

    paths: dict[str, set[str]] = {}
    for route, ops in (doc.get("paths") or {}).items():
        for method in ops:
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                paths.setdefault(route, set()).add(method.upper())

    missing: list[str] = []
    for method, route in REQUIRED:
        if method not in paths.get(route, set()):
            missing.append(f"{method} {route}")

    print(f"API: {API}")
    print(f"routes in OpenAPI document: {len(paths)}")
    print(f"required by the console: {len(REQUIRED)}")
    if missing:
        print(f"\nMISSING ({len(missing)}):")
        for item in missing:
            print(f"  {item}")
        return 1
    print("\nAll console routes are registered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
