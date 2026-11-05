"""Booking a guest must really email the invitation, and the agent must be told whether it did."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from server.services.integration_calendar import execute_calendar_action

BASE = "https://gateway.test"


def _client(seen: list[httpx.Request], attendees: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/freeBusy"):
            return httpx.Response(200, json={"calendars": {"primary": {"busy": []}}})
        if request.method == "POST" and request.url.path.endswith("/events"):
            return httpx.Response(200, json={"id": "evt-1", "attendees": attendees})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _book(params: dict, attendees: list[dict]):
    seen: list[httpx.Request] = []
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)

    async def run():
        async with _client(seen, attendees) as client:
            return await execute_calendar_action(client, BASE, {}, "GOOGLECALENDAR_CREATE_EVENT", {
                "summary": "Site visit", "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), **params,
            })

    return asyncio.run(run()), seen


def test_booking_with_a_guest_asks_google_to_email_the_invitation():
    result, seen = _book({"attendee_email": "caller@example.com"}, [{"email": "caller@example.com"}])
    create = next(r for r in seen if r.method == "POST" and r.url.path.endswith("/events"))
    assert create.url.params.get("sendUpdates") == "all"
    assert result["status"] == "success" and result["invitation_sent"] is True
    assert "invitation was emailed to caller@example.com" in result["summary"]


def test_booking_without_a_guest_says_no_invitation_was_sent():
    result, seen = _book({}, [])
    create = next(r for r in seen if r.method == "POST" and r.url.path.endswith("/events"))
    assert "sendUpdates" not in create.url.params
    assert result["invitation_sent"] is False
    assert "No invitation email was sent" in result["summary"]
