"""Explicitly guarded local helper for an operator-approved outbound test call.

Normal invocation is a dry run. It makes no HTTP requests. To dial, provide
operator-owned test values through environment variables and pass ``--live``
with ``DIALTACT_ALLOW_REAL_TEST_CALLS=1`` set.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Mapping, Sequence
from urllib.parse import quote, urlsplit
import uuid

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


@dataclass(frozen=True)
class LiveCallConfig:
    base_url: str
    to_e164: str = field(repr=False)
    agent_id: str = field(repr=False)
    username: str = field(repr=False)
    password: str = field(repr=False)
    talk_seconds: int


def resolve_live_config(
    *, live_requested: bool, talk_seconds: int, environ: Mapping[str, str] | None = None
) -> LiveCallConfig:
    """Validate every opt-in before a network client can be created."""
    env = os.environ if environ is None else environ
    if not live_requested:
        raise ValueError("Live calling is disabled. Use the default mock-only mode.")
    if env.get("DIALTACT_ALLOW_REAL_TEST_CALLS") != "1":
        raise ValueError("Set DIALTACT_ALLOW_REAL_TEST_CALLS=1 to explicitly enable a real call.")
    if not 5 <= talk_seconds <= 300:
        raise ValueError("talk_seconds must be between 5 and 300.")

    base_url = (env.get("DIALTACT_TEST_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("The test API URL must be a plain HTTP loopback origin.")

    required = {
        "to_e164": env.get("DIALTACT_TEST_CALL_TO_E164", "").strip(),
        "agent_id": env.get("DIALTACT_TEST_CALL_AGENT_ID", "").strip(),
        "username": env.get("DIALTACT_DEV_USERNAME", "").strip(),
        "password": env.get("DIALTACT_DEV_PASSWORD", ""),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError("Missing required operator test-call configuration: " + ", ".join(missing))
    if not _E164.fullmatch(required["to_e164"]):
        raise ValueError("The test destination must use E.164 format.")
    try:
        uuid.UUID(required["agent_id"])
    except ValueError as exc:
        raise ValueError("The test agent id must be a UUID.") from exc
    return LiveCallConfig(base_url=base_url, talk_seconds=talk_seconds, **required)


async def _run_live_call(config: LiveCallConfig) -> int:
    try:
        async with httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(15.0, connect=3.0),
            follow_redirects=False,
        ) as client:
            login = await client.post(
                "/api/dev/login",
                json={"username": config.username, "password": config.password},
            )
            if login.status_code != 200:
                print("login failed", login.status_code)
                return 1
            csrf = client.cookies.get("dev_csrf") or ""
            headers = {"X-CSRF-Token": csrf} if csrf else {}
            dial = await client.post(
                "/api/dev/telephony/outbound",
                json={
                    "toE164": config.to_e164,
                    "agentId": config.agent_id,
                    "tier": "medium",
                    "language": "te-IN",
                },
                headers=headers,
            )
            if dial.status_code != 200:
                print("dial request failed", dial.status_code)
                return 1
            try:
                dial_body = dial.json()
            except ValueError:
                print("dial request returned an invalid response")
                return 1
            if not isinstance(dial_body, dict) or dial_body.get("ok") is False:
                print("dial request failed", dial.status_code)
                return 1

            print("A live test call was requested. Answer the operator-owned test phone.")
            print("Speak Telugu, then hang up. The helper will wait for hangup completion.")
            call_id = str(dial_body.get("call_id") or dial_body.get("callId") or dial_body.get("id") or "")
            query = f"?call_id={quote(call_id, safe='')}" if call_id else ""
            active_seen = False
            for _ in range(config.talk_seconds // 5):
                await asyncio.sleep(5)
                flow_response = await client.get(f"/api/dev/telephony/media-flow{query}", headers=headers)
                if flow_response.status_code != 200:
                    continue
                try:
                    flow_body = flow_response.json()
                except ValueError:
                    continue
                flow = flow_body.get("flow") if isinstance(flow_body, dict) else None
                if not isinstance(flow, dict):
                    continue
                if flow.get("active") is True:
                    active_seen = True
                stages = flow.get("stages") or {}
                events = flow.get("events") or []
                hangup_complete = bool(stages.get("hangup_complete")) or any(
                    isinstance(event, dict) and event.get("stage") == "hangup_complete"
                    for event in events
                )
                if hangup_complete:
                    print("Call hangup completion observed.")
                    return 0
                if active_seen and flow.get("active") is False:
                    print("Call ended without a hangup-completion event.")
                    return 1

            print("Timed out before hangup completion was observed.")
            return 1
    except httpx.HTTPError:
        print("The local test API request failed.")
        return 1


async def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Enable the explicitly configured real-call path")
    parser.add_argument("--talk-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if not args.live:
        print("Mock-only dry run: no call was placed and no network request was sent.")
        return 0
    try:
        config = resolve_live_config(live_requested=True, talk_seconds=args.talk_seconds)
    except ValueError as exc:
        print(f"Refusing live call: {exc}")
        return 2
    return await _run_live_call(config)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
