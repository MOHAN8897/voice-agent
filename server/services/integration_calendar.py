"""Google Calendar actions with explicit dates and fail-closed availability."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from server.services.integration_safety import path_segment


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


async def execute_calendar_action(client: httpx.AsyncClient, base: str, headers: dict, action: str, params: dict) -> dict:
    mutation_started = False
    try:
        calendar = str(params.get("calendar_id") or "primary")
        root = f"{base}/proxy/calendar/v3/calendars/{path_segment(calendar)}"
        if action in {"GOOGLECALENDAR_FIND_FREE_SLOTS", "GOOGLECALENDAR_FIND_SLOTS", "GOOGLECALENDAR_LIST_EVENTS"}:
            metadata = await client.get(root, headers=headers)
            metadata.raise_for_status()
            zone = ZoneInfo(metadata.json()["timeZone"])
            target = date.fromisoformat(str(params.get("date") or ""))
            start = datetime.combine(target, time.min, zone)
            end = start + timedelta(days=1)
            if action == "GOOGLECALENDAR_LIST_EVENTS":
                response = await client.get(f"{root}/events", headers=headers, params={
                    "timeMin": start.isoformat(), "timeMax": end.isoformat(), "singleEvents": "true",
                    "orderBy": "startTime", "maxResults": 10,
                })
                response.raise_for_status()
                events = [{k: event[k] for k in ("id", "summary", "start", "end") if k in event} for event in response.json().get("items", [])]
                return {"status": "success", "events": events, "summary": f"Retrieved {len(events)} calendar events."}
            duration = int(params.get("duration") or 30)
            if not 5 <= duration <= 480:
                raise ValueError("Invalid duration")
            busy = await _busy(client, base, headers, start, end, calendar)
            # Samples of calendar free time are not a promise of business hours.
            cursor = datetime.combine(target, time(9), zone)
            stop = datetime.combine(target, time(17), zone)
            slots: list[str] = []
            while cursor + timedelta(minutes=duration) <= stop and len(slots) < 8:
                finish = cursor + timedelta(minutes=duration)
                if cursor > datetime.now(timezone.utc) and not any(cursor < b_end and finish > b_start for b_start, b_end in busy):
                    slots.append(cursor.isoformat())
                cursor += timedelta(minutes=30)
            return {"status": "available" if slots else "unavailable", "available_slots": slots,
                    "date": target.isoformat(), "time_zone": str(zone),
                    "message": "Calendar free-time samples between 09:00 and 17:00; confirm the business's appointment hours before booking."}
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
