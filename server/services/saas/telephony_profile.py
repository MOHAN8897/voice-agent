"""Agent telephony configuration — persistence plus the pure routing decision.

Two consumers, one source of truth:

* the console reads/writes it through the subscriber API;
* the live inbound PSTN path calls :func:`evaluate_inbound_policy` to decide whether
  to answer, and what the caller hears.

:func:`evaluate_inbound_policy` is deliberately pure and total: any missing or
malformed input yields the legacy "always answer, no override" decision, so a bad
config can never drop a live call.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timezone as dt_timezone
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.phase5_models import AgentTelephonyProfile

DEFAULT_TIMEZONE: Final = "Asia/Kolkata"
AFTER_HOURS_ACTIONS: Final[tuple[str, ...]] = ("voicemail", "hangup", "transfer", "always")
WEEKDAYS: Final[tuple[str, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
#: Reserved business_hours keys for YYYY-MM-DD holiday closures (no DB migration).
CLOSED_KEYS: Final[frozenset[str]] = frozenset({"closed", "closed_dates", "holidays"})
MAX_GREETING_CHARS: Final = 500
MAX_CLOSED_DATES: Final = 60

#: Decision vocabulary returned to the ingress and surfaced in the console.
ROUTE_AGENT: Final = "agent"
ROUTE_VOICEMAIL: Final = "voicemail"
ROUTE_TRANSFER: Final = "transfer"
ROUTE_DECLINE: Final = "decline"

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

#: Every phone number in this product is Indian unless a tenant says otherwise.
_DEFAULT_TZ_OFFSET = dt_timezone.utc


class TelephonyProfileError(ValueError):
    """Raised for a profile payload the API must reject."""


@dataclass(frozen=True)
class InboundDecision:
    """What the ingress should do with one inbound attempt."""

    #: True when the call should be answered at all.
    should_answer: bool
    #: One of ROUTE_AGENT / ROUTE_VOICEMAIL / ROUTE_TRANSFER / ROUTE_DECLINE.
    route: str
    #: Stable machine-readable reason, recorded on the attempt for auditability.
    reason: str
    #: Business hours were consulted and the call landed outside them.
    after_hours: bool = False
    #: Spoken opening, or None to derive it from the compiled brain as today.
    greeting_phrase: str | None = None
    #: True when no usable profile was found and the legacy path is being used.
    used_fallback: bool = False
    #: Populated when the destination number matched an agent.
    agent_id: str | None = None
    #: Destination phone number for after_hours_action == "transfer".
    transfer_number: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "shouldAnswer": self.should_answer,
            "route": self.route,
            "reason": self.reason,
            "afterHours": self.after_hours,
            "greetingPhrase": self.greeting_phrase,
            "usedFallback": self.used_fallback,
            "agentId": self.agent_id,
            "transferNumber": self.transfer_number,
        }


def default_decision() -> InboundDecision:
    """The legacy behaviour: answer and let the brain drive the greeting."""
    return InboundDecision(
        should_answer=True,
        route=ROUTE_AGENT,
        reason="no_profile",
        used_fallback=True,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def normalize_timezone(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_TIMEZONE
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise TelephonyProfileError("timezone must be a valid IANA zone such as Asia/Kolkata")
    return raw


def normalize_greeting_phrase(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    if len(text) > MAX_GREETING_CHARS:
        raise TelephonyProfileError(f"greeting phrase must be {MAX_GREETING_CHARS} characters or fewer")
    return text


def normalize_after_hours_action(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "voicemail"
    if raw not in AFTER_HOURS_ACTIONS:
        raise TelephonyProfileError(f"after_hours_action must be one of {', '.join(AFTER_HOURS_ACTIONS)}")
    return raw


def normalize_transfer_number(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if not _E164_RE.match(raw):
        raise TelephonyProfileError("transfer number must be E.164, for example +14155552671")
    return raw


def normalize_closed_dates(value: Any) -> list[str]:
    """Accept ``["2026-12-25"]`` or a newline/comma-separated string. Cap length."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw_items = re.split(r"[\s,;]+", value.strip())
    elif isinstance(value, list):
        raw_items = value
    else:
        raise TelephonyProfileError("closedDates must be a list of YYYY-MM-DD strings")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        raw = str(item or "").strip()
        if not raw:
            continue
        if not _DATE_RE.match(raw):
            raise TelephonyProfileError(f"closedDates entry must be YYYY-MM-DD, got {raw!r}")
        if raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
        if len(out) > MAX_CLOSED_DATES:
            raise TelephonyProfileError(f"closedDates supports at most {MAX_CLOSED_DATES} dates")
    return out


def normalize_business_hours(value: Any) -> dict[str, Any]:
    """Accept weekday windows plus optional ``closed`` holiday dates.

    ``{"mon": [{"open": "09:00", "close": "18:00"}], "closed": ["2026-12-25"]}``.
    An empty object means "always open". Holidays alone close those dates only.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TelephonyProfileError("businessHours must be an object keyed by weekday")
    out: dict[str, Any] = {}
    closed: list[str] = []
    for raw_day, windows in value.items():
        day = str(raw_day or "").strip().lower()
        if day in CLOSED_KEYS:
            closed = normalize_closed_dates(windows)
            continue
        if day not in WEEKDAYS:
            raise TelephonyProfileError(f"businessHours keys must be one of {', '.join(WEEKDAYS)}")
        if not isinstance(windows, list):
            raise TelephonyProfileError(f"businessHours.{day} must be a list of opening windows")
        parsed: list[dict[str, str]] = []
        for window in windows:
            if not isinstance(window, dict):
                raise TelephonyProfileError(f"businessHours.{day} entries must be objects")
            open_raw = str(window.get("open") or "").strip()
            close_raw = str(window.get("close") or "").strip()
            if not _TIME_RE.match(open_raw) or not _TIME_RE.match(close_raw):
                raise TelephonyProfileError("businessHours windows must use 24h HH:MM times")
            if open_raw == close_raw:
                raise TelephonyProfileError("businessHours window must have different open and close times")
            parsed.append({"open": open_raw, "close": close_raw})
        if parsed:
            out[day] = parsed
    if closed:
        out["closed"] = closed
    return out


# ---------------------------------------------------------------------------
# Business hours evaluation
# ---------------------------------------------------------------------------


def _parse_hhmm(value: str) -> time | None:
    match = _TIME_RE.match(value or "")
    if not match:
        return None
    return time(int(match.group(1)), int(match.group(2)))


def validate_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a partial camelCase API payload into snake_case storage fields.

    Unset (``None``) fields are dropped so ``update_profile`` keeps the current
    value rather than silently resetting it.
    """
    out: dict[str, Any] = {}
    for key in (
        "greeting_phrase",
        "business_hours",
        "timezone",
        "after_hours_action",
        "transfer_number",
        "inbound_enabled",
        "outbound_enabled",
    ):
        if payload.get(key) is not None:
            out[key] = payload[key]
    return out


def resolve_zone(tz_name: str) -> Any:
    try:
        return ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return dt_timezone(_DEFAULT_TZ_OFFSET.utcoffset(None) or dt_timezone.utc.utcoffset(None))


def is_within_business_hours(
    business_hours: Any,
    *,
    tz_name: str = DEFAULT_TIMEZONE,
    at: datetime | None = None,
) -> bool:
    """True when ``at`` falls inside a configured window. No config = always open.

    Never raises: malformed hours are treated as "always open" so a bad config
    cannot silence a live number. Dates in ``closed`` are always outside hours.
    """
    if not isinstance(business_hours, dict) or not business_hours:
        return True
    zone = resolve_zone(tz_name)
    moment = at or datetime.now(dt_timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    local = moment.astimezone(zone)
    closed = business_hours.get("closed")
    if isinstance(closed, list) and local.date().isoformat() in closed:
        return False
    day_windows = {k: v for k, v in business_hours.items() if k in WEEKDAYS}
    if not day_windows:
        return True
    day = WEEKDAYS[local.weekday()]
    windows = day_windows.get(day)
    if not isinstance(windows, list) or not windows:
        return False
    now_t = local.time()
    for window in windows:
        if not isinstance(window, dict):
            continue
        opens = _parse_hhmm(str(window.get("open") or ""))
        closes = _parse_hhmm(str(window.get("close") or ""))
        if opens is None or closes is None:
            continue
        if opens <= closes:
            if opens <= now_t < closes:
                return True
        else:
            # Window crosses midnight, e.g. 22:00 → 02:00.
            if now_t >= opens or now_t < closes:
                return True
    return False


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def evaluate_inbound_policy(
    profile: Any,
    *,
    at: datetime | None = None,
) -> InboundDecision:
    """Decide what happens to one inbound attempt. Pure and total.

    A ``None`` profile, or one with unusable values, produces exactly today's
    behaviour (answer, brain greeting) and is flagged ``used_fallback``.
    """
    if profile is None:
        return default_decision()

    data = profile if isinstance(profile, dict) else _profile_to_dict(profile)
    agent_id = data.get("agent_id")

    try:
        agent_status = str(data.get("agent_status") or "").strip().lower()
        if agent_status in ("paused", "inactive", "disabled"):
            return InboundDecision(
                should_answer=False,
                route=ROUTE_DECLINE,
                reason="agent_paused",
                agent_id=agent_id,
            )
        if data.get("inbound_enabled") is False:
            return InboundDecision(
                should_answer=False,
                route=ROUTE_DECLINE,
                reason="inbound_disabled",
                agent_id=agent_id,
            )
        tz_name = normalize_timezone(data.get("timezone"))
        hours = normalize_business_hours(data.get("business_hours"))
        action = normalize_after_hours_action(data.get("after_hours_action"))
        greeting = normalize_greeting_phrase(data.get("greeting_phrase"))
        transfer_number = normalize_transfer_number(data.get("transfer_number"))
    except TelephonyProfileError:
        # Malformed config must never change live call handling.
        return InboundDecision(
            should_answer=True,
            route=ROUTE_AGENT,
            reason="invalid_profile",
            used_fallback=True,
            agent_id=agent_id,
        )

    if action == "always" or not hours:
        return InboundDecision(
            should_answer=True,
            route=ROUTE_AGENT,
            reason="in_hours" if hours else "no_hours_configured",
            greeting_phrase=greeting,
            agent_id=agent_id,
        )

    if is_within_business_hours(hours, tz_name=tz_name, at=at):
        return InboundDecision(
            should_answer=True,
            route=ROUTE_AGENT,
            reason="in_hours",
            greeting_phrase=greeting,
            agent_id=agent_id,
        )

    if action == "hangup":
        return InboundDecision(
            should_answer=False,
            route=ROUTE_DECLINE,
            reason="after_hours_hangup",
            after_hours=True,
            greeting_phrase=greeting,
            agent_id=agent_id,
        )
    if action == "transfer":
        if not transfer_number:
            # Misconfigured transfer: keep taking the call rather than dropping it.
            return InboundDecision(
                should_answer=True,
                route=ROUTE_AGENT,
                reason="after_hours_transfer_unconfigured",
                after_hours=True,
                greeting_phrase=greeting,
                agent_id=agent_id,
            )
        return InboundDecision(
            should_answer=True,
            route=ROUTE_TRANSFER,
            reason="after_hours_transfer",
            after_hours=True,
            greeting_phrase=greeting,
            agent_id=agent_id,
            transfer_number=transfer_number,
        )
    return InboundDecision(
        should_answer=True,
        route=ROUTE_VOICEMAIL,
        reason="after_hours_voicemail",
        after_hours=True,
        greeting_phrase=greeting,
        agent_id=agent_id,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _profile_to_dict(row: AgentTelephonyProfile) -> dict[str, Any]:
    return {
        "profile_id": str(row.profile_id),
        "agent_id": str(row.agent_id),
        "tenant_id": str(row.tenant_id),
        "greeting_phrase": row.greeting_phrase,
        "business_hours": row.business_hours or {},
        "timezone": row.timezone,
        "after_hours_action": row.after_hours_action,
        "transfer_number": row.transfer_number,
        "inbound_enabled": bool(row.inbound_enabled),
        "outbound_enabled": bool(row.outbound_enabled),
    }


def public_profile(data: dict[str, Any]) -> dict[str, Any]:
    """camelCase contract shared by the API and the console."""
    hours = data.get("business_hours") or {}
    closed = hours.get("closed") if isinstance(hours, dict) else []
    day_hours = {
        day: list(windows)
        for day, windows in hours.items()
        if day in WEEKDAYS and isinstance(windows, list)
    }
    return {
        "agentId": str(data.get("agent_id") or ""),
        "greetingPhrase": data.get("greeting_phrase") or "",
        "businessHours": day_hours,
        "closedDates": list(closed) if isinstance(closed, list) else [],
        "timezone": data.get("timezone") or DEFAULT_TIMEZONE,
        "afterHoursAction": data.get("after_hours_action") or "voicemail",
        "transferNumber": data.get("transfer_number") or "",
        "inboundEnabled": bool(data.get("inbound_enabled", True)),
        "outboundEnabled": bool(data.get("outbound_enabled", True)),
        "hasProfile": True,
    }


async def get_profile(agent_id: str) -> dict[str, Any] | None:
    """Read a profile without creating one. ``None`` means "use legacy behaviour"."""
    try:
        aid = uuid.UUID(str(agent_id))
    except (ValueError, TypeError):
        return None
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        result = await session.execute(
            select(AgentTelephonyProfile).where(AgentTelephonyProfile.agent_id == aid)
        )
        row = result.scalar_one_or_none()
        return _profile_to_dict(row) if row is not None else None


async def get_or_create_profile(agent_id: str, tenant_id: str) -> dict[str, Any]:
    """Read, or lazily create defaults so the console always has something to show."""
    existing = await get_profile(agent_id)
    if existing is not None:
        return existing
    try:
        aid = uuid.UUID(str(agent_id))
        tid = uuid.UUID(str(tenant_id))
    except (ValueError, TypeError):
        raise TelephonyProfileError("invalid agent")
    factory = get_session_factory()
    if factory is None:
        return {
            "agent_id": str(agent_id),
            "tenant_id": str(tenant_id),
            "greeting_phrase": None,
            "business_hours": {},
            "timezone": DEFAULT_TIMEZONE,
            "after_hours_action": "voicemail",
            "transfer_number": None,
            "inbound_enabled": True,
            "outbound_enabled": True,
        }
    async with factory() as session:
        result = await session.execute(
            select(AgentTelephonyProfile).where(AgentTelephonyProfile.agent_id == aid)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentTelephonyProfile(
                profile_id=uuid.uuid4(),
                agent_id=aid,
                tenant_id=tid,
                business_hours={},
                timezone=DEFAULT_TIMEZONE,
                after_hours_action="voicemail",
                inbound_enabled=True,
                outbound_enabled=True,
            )
            session.add(row)
            try:
                await session.commit()
            except Exception:
                # Lost a create race — re-read the winner.
                await session.rollback()
                result = await session.execute(
                    select(AgentTelephonyProfile).where(AgentTelephonyProfile.agent_id == aid)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    raise
        await session.refresh(row)
        return _profile_to_dict(row)


async def update_profile(agent_id: str, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate then persist. Raises :class:`TelephonyProfileError` on bad input."""
    greeting = normalize_greeting_phrase(payload.get("greeting_phrase"))
    hours = normalize_business_hours(payload.get("business_hours"))
    tz_name = normalize_timezone(payload.get("timezone"))
    action = normalize_after_hours_action(payload.get("after_hours_action"))
    transfer = normalize_transfer_number(payload.get("transfer_number"))
    if action == "transfer" and not transfer:
        raise TelephonyProfileError("a transfer number is required when after_hours_action is 'transfer'")

    current = await get_or_create_profile(agent_id, tenant_id)
    try:
        aid = uuid.UUID(str(agent_id))
    except (ValueError, TypeError):
        raise TelephonyProfileError("invalid agent")

    factory = get_session_factory()
    if factory is None:
        return {
            "agent_id": str(agent_id),
            "tenant_id": str(tenant_id),
            "greeting_phrase": greeting,
            "business_hours": hours,
            "timezone": tz_name,
            "after_hours_action": action,
            "transfer_number": transfer,
            "inbound_enabled": bool(payload.get("inbound_enabled", current.get("inbound_enabled", True))),
            "outbound_enabled": bool(payload.get("outbound_enabled", current.get("outbound_enabled", True))),
        }

    async with factory() as session:
        result = await session.execute(
            select(AgentTelephonyProfile).where(AgentTelephonyProfile.agent_id == aid)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentTelephonyProfile(profile_id=uuid.uuid4(), agent_id=aid, tenant_id=uuid.UUID(str(tenant_id)))
            session.add(row)
        row.greeting_phrase = greeting
        row.business_hours = hours
        row.timezone = tz_name
        row.after_hours_action = action
        row.transfer_number = transfer
        row.inbound_enabled = bool(payload.get("inbound_enabled", True))
        row.outbound_enabled = bool(payload.get("outbound_enabled", True))
        await session.commit()
        await session.refresh(row)
        return _profile_to_dict(row)


async def profile_for_number(e164: str | None) -> dict[str, Any] | None:
    """Resolve the agent behind a destination number, then that agent's profile.

    Only lines already assigned to an agent are considered, so an unassigned number
    keeps today's behaviour.
    """
    raw = str(e164 or "").strip()
    if not raw:
        return None
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        from server.db.models.entities import Agent
        from server.db.models.phase5_models import PhoneNumber

        result = await session.execute(
            select(PhoneNumber, Agent)
            .outerjoin(Agent, Agent.agent_id == PhoneNumber.agent_id)
            .where(
                PhoneNumber.e164 == raw,
                PhoneNumber.released_at.is_(None),
            )
        )
        row = result.first()
        if row is None or row[0] is None or row[0].agent_id is None:
            return None
        pn, agent = row
        agent_id = str(pn.agent_id)
        agent_status = str(agent.status or "active") if agent else "active"
        tenant_id = str(pn.tenant_id) if pn.tenant_id else (str(agent.tenant_id) if agent and agent.tenant_id else "")

    prof = await get_profile(agent_id)
    if prof is not None:
        prof["agent_status"] = agent_status
        if not prof.get("tenant_id") and tenant_id:
            prof["tenant_id"] = tenant_id
        return prof
    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "agent_status": agent_status,
        "inbound_enabled": True,
        "outbound_enabled": True,
    }


async def profile_for_agent_ids(agent_ids: list[str]) -> dict[str, dict[str, Any] | None]:
    """Batch read for list endpoints. Missing profiles map to ``None``."""
    out: dict[str, dict[str, Any] | None] = {aid: None for aid in agent_ids}
    factory = get_session_factory()
    if factory is None:
        return out
    parsed: list[uuid.UUID] = []
    for aid in agent_ids:
        try:
            parsed.append(uuid.UUID(aid))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return out
    async with factory() as session:
        result = await session.execute(
            select(AgentTelephonyProfile).where(AgentTelephonyProfile.agent_id.in_(parsed))
        )
        for row in result.scalars():
            out[str(row.agent_id)] = _profile_to_dict(row)
    return out
