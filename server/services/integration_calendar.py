"""Google Calendar actions with explicit dates and fail-closed availability."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import hashlib

import httpx

from server.services.integration_safety import path_segment, spread


def _instant(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Date and time must include an offset")
    return parsed


async def _busy(client: httpx.AsyncClient, base: str, headers: dict, start: datetime, end: datetime, calendar: str = "primary") -> list:
    response = await client.post(f"{base}/proxy/calendar/v3/freeBusy", headers=headers, json={
        "timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": calendar}],
    })
    response.raise_for_status()
    result = response.json().get("calendars", {}).get(calendar)
    if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("busy"), list):
        raise ValueError("Calendar availability could not be verified")
    spans = [(_instant(span["start"]), _instant(span["end"])) for span in result["busy"]]
    if any(end <= start for start, end in spans):
        raise ValueError("Invalid busy interval")
    return spans


PARTY_KEY = "dialtact_party"


def party_tag(phone_digits: str) -> str:
    """Stored on events the agent books, so the same caller can find them later
    without the agent ever reading other people's appointments."""
    return hashlib.sha256(f"dialtact-party:{phone_digits}".encode()).hexdigest()[:32] if phone_digits else ""


def _owned_by_caller(event: dict, tag: str, email: str) -> bool:
    private = ((event.get("extendedProperties") or {}).get("private") or {})
    if tag and private.get(PARTY_KEY) == tag:
        return True
    wanted = email.strip().casefold()
    return bool(wanted) and any(str(a.get("email") or "").casefold() == wanted for a in event.get("attendees") or [])


def _hhmm(value: Any, default: time) -> time:
    try:
        hour, minute = str(value).split(":")
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return default


async def execute_calendar_action(client: httpx.AsyncClient, base: str, headers: dict, action: str, params: dict,
                                  context: dict | None = None) -> dict:
    mutation_started = False
    tag = party_tag(str((context or {}).get("party_phone") or ""))
    email = str(params.get("attendee_email") or "")
    try:
        calendar = str(params.get("calendar_id") or "primary")
        root = f"{base}/proxy/calendar/v3/calendars/{path_segment(calendar)}"
        if action in {"GOOGLECALENDAR_FIND_FREE_SLOTS", "GOOGLECALENDAR_FIND_SLOTS", "GOOGLECALENDAR_LIST_EVENTS"}:
            metadata = await client.get(root, headers=headers)
            metadata.raise_for_status()
            zone = ZoneInfo(metadata.json()["timeZone"])
            target = date.fromisoformat(str(params.get("date") or ""))
            if action != "GOOGLECALENDAR_LIST_EVENTS" and target < datetime.now(zone).date():
                raise ValueError("Choose a current or future date")
            start = datetime.combine(target, time.min, zone)
            end = start + timedelta(days=1)
            if action == "GOOGLECALENDAR_LIST_EVENTS":
                if not tag and not email:
                    return {"status": "error", "message": "Ask for the email the appointment was booked with."}
                response = await client.get(f"{root}/events", headers=headers, params={
                    "timeMin": start.isoformat(), "timeMax": end.isoformat(), "singleEvents": "true",
                    "orderBy": "startTime", "maxResults": 250,
                })
                response.raise_for_status()
                # Only this caller's appointments: other bookings hold other people's details.
                events = [{k: event[k] for k in ("id", "summary", "start", "end") if k in event}
                          for event in response.json().get("items", [])
                          if event.get("status") != "cancelled" and _owned_by_caller(event, tag, email)]
                return {"status": "success" if events else "not_found", "events": events,
                        "summary": f"Found {len(events)} appointment(s) for this caller."}
            duration = int(params.get("duration") or 30)
            if not 5 <= duration <= 480:
                raise ValueError("Invalid duration")
            busy = await _busy(client, base, headers, start, end, calendar)
            # Samples of calendar free time are not a promise of business hours.
            cursor = datetime.combine(target, _hhmm(params.get("day_start"), time(9)), zone)
            stop = datetime.combine(target, _hhmm(params.get("day_end"), time(17)), zone)
            # The whole bookable day, not just its first hours: a caller asking
            # for the afternoon must be offered afternoon times.
            starts: list[datetime] = []
            while cursor + timedelta(minutes=duration) <= stop and len(starts) < 48:
                finish = cursor + timedelta(minutes=duration)
                if cursor > datetime.now(timezone.utc) and not any(cursor < b_end and finish > b_start for b_start, b_end in busy):
                    starts.append(cursor)
                cursor += timedelta(minutes=30)
            ranges: list[list[datetime]] = []
            for slot in starts:
                if ranges and slot - ranges[-1][1] == timedelta(minutes=30):
                    ranges[-1][1] = slot
                else:
                    ranges.append([slot, slot])
            return {"status": "available" if starts else "unavailable",
                    "available_slots": [s.isoformat() for s in spread(starts)],
                    "free_ranges": [f"{a:%H:%M}-{b + timedelta(minutes=duration):%H:%M}" for a, b in ranges],
                    "date": target.isoformat(), "time_zone": str(zone),
                    "message": "Free times within the business's bookable hours "
                               f"{_hhmm(params.get('day_start'), time(9)):%H:%M}-{_hhmm(params.get('day_end'), time(17)):%H:%M}."}
        if action in {"GOOGLECALENDAR_CANCEL_EVENT", "GOOGLECALENDAR_DELETE_EVENT",
                      "GOOGLECALENDAR_RESCHEDULE_EVENT", "GOOGLECALENDAR_UPDATE_EVENT"}:
            current = await client.get(f"{root}/events/{path_segment(params.get('event_id') or '')}", headers=headers)
            if current.status_code == 404:
                return {"status": "not_found", "message": "That appointment was not found. Nothing was changed."}
            current.raise_for_status()
            if not _owned_by_caller(current.json(), tag, email):
                return {"status": "error", "message": "That appointment could not be matched to this caller. Nothing was changed."}
        if action in {"GOOGLECALENDAR_CANCEL_EVENT", "GOOGLECALENDAR_DELETE_EVENT"}:
            event_id = path_segment(params.get('event_id') or '')
            mutation_started = True
            response = await client.delete(f"{root}/events/{event_id}", headers=headers)
            response.raise_for_status()
            if response.status_code not in {200, 204}:
                return {"status": "unknown", "message": "Check the calendar to confirm cancellation."}
            return {"status": "cancelled", "event_id": params["event_id"], "summary": "Calendar event cancelled."}
        start = _instant(params.get("start") or params.get("start_time"))
        end = _instant(params.get("end") or params.get("end_time"))
        if end <= start or start <= datetime.now(timezone.utc):
            raise ValueError("Choose a future start and a later end")
        reschedule = action in {"GOOGLECALENDAR_RESCHEDULE_EVENT", "GOOGLECALENDAR_UPDATE_EVENT"}
        event_id = str(params.get("event_id") or "")
        if reschedule:
            # FreeBusy includes the event being moved. Inspect overlapping events
            # instead so an unchanged or partially overlapping booking is valid.
            response = await client.get(f"{root}/events", headers=headers, params={
                "timeMin": start.isoformat(), "timeMax": end.isoformat(), "singleEvents": "true", "maxResults": 250,
            })
            response.raise_for_status()
            data = response.json()
            if data.get("nextPageToken") or not isinstance(data.get("items"), list):
                raise ValueError("Availability requires a wider calendar review")
            conflicts = [e for e in data.get("items", []) if e.get("id") != event_id and e.get("status") != "cancelled" and e.get("transparency") != "transparent"]
        else:
            conflicts = await _busy(client, base, headers, start, end, calendar)
        if conflicts:
            return {"status": "conflict", "confirmed": False, "message": "That time overlaps an existing calendar event. No booking was changed."}
        payload: dict[str, Any] = {"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}
        if reschedule and params.get("summary"):
            payload["summary"] = params["summary"]
        if reschedule:
            encoded_id = path_segment(event_id)
            mutation_started = True
            response = await client.patch(f"{root}/events/{encoded_id}", headers=headers, json=payload)
        else:
            if not str(params.get("summary") or "").strip():
                raise ValueError("Event title required")
            payload.update(summary=params["summary"], description=params.get("description") or "")
            if params.get("attendee_email"):
                payload["attendees"] = [{"email": params["attendee_email"]}]
            if tag:
                payload["extendedProperties"] = {"private": {PARTY_KEY: tag}}
            mutation_started = True
            response = await client.post(f"{root}/events", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        if not result.get("id"):
            return {"status": "unknown", "message": "The calendar returned no verifiable event. Check the calendar before trying again."}
        return {"status": "success", "confirmed": True, "event_id": result["id"], "rescheduled": reschedule,
                "date": start.date().isoformat(), "time": start.isoformat(), "summary": "Calendar event updated." if reschedule else "Calendar event created."}
    except httpx.HTTPStatusError as exc:
        return {"status": "error" if exc.response.status_code < 500 else "unknown", "message": "The calendar request could not be completed or verified."}
    except (ValueError, KeyError, TypeError):
        if mutation_started:
            return {"status": "unknown", "message": "The calendar result could not be verified. Check it before trying again."}
        return {"status": "error", "message": "Calendar details or availability could not be verified. No booking was started."}
