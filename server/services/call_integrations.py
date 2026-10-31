"""Per-call and per-campaign integration selection.

The tenant connects apps on the Integrations page. When a single call or a
campaign is launched, it may attach a subset of those apps, each in one mode:

* ``in_call``  - the model may use the app's actions while talking.
* ``post_call`` - the platform runs one well-defined action after the call,
  built from the call outcome (never from model arguments).

Runtime rule for a call that carries a selection::

    exposed = selected(mode) ∩ connected-and-verified ∩ agent-allowed

A call with no selection (``None``) keeps the agent's saved integration rules.

Only apps listed in :data:`CALL_INTEGRATION_PROFILES` can be attached. Apps in
the catalog whose actions need resource ids nobody has configured (a Slack
channel, a ClickUp list, a Notion parent ...) are returned as ``setup_required``
so the console shows them disabled instead of letting them fail mid-call.
"""
from __future__ import annotations

import re
import time
import uuid
from collections import OrderedDict
from typing import Any, Iterable

from server.utils.logger import logger

MODES = ("in_call", "post_call")
MAX_SELECTED = 12

# Plain-language explanations shown to the tenant and used in the call prompt.
CALL_INTEGRATION_PROFILES: dict[str, dict[str, Any]] = {
    "GOOGLECALENDAR": {
        "in_call": "Check free times and book, move or cancel appointments in Google Calendar during the call.",
    },
    "CALENDLY": {
        "in_call": "Look up open Calendly times and book the caller into a meeting during the call (booking needs a paid Calendly plan).",
    },
    "ZOOM": {
        "in_call": "Create a Zoom meeting link for the caller during the call.",
    },
    "HUBSPOT": {
        "in_call": "Look up the caller in HubSpot and create contacts, deals or notes during the call.",
        "post_call": "Create the caller as a HubSpot contact after the call, when their name was captured.",
    },
    "SALESFORCE": {
        "in_call": "Look up or create the caller as a Salesforce lead and log follow-up tasks during the call.",
    },
    "ZENDESK": {
        "in_call": "Look up, open or update the caller's Zendesk support tickets during the call.",
    },
    "INTERCOM": {
        "in_call": "Find the caller in Intercom and open a conversation for the team during the call.",
    },
    "FRESHDESK": {
        "in_call": "Look up or open Freshdesk support tickets for the caller during the call.",
    },
    "SHOPIFY": {
        "in_call": "Look up the caller's Shopify orders and delivery status, and cancel an order when asked, during the call.",
    },
    "WOOCOMMERCE": {
        "in_call": "Look up WooCommerce orders and stock, and update an order status, during the call.",
    },
    "GMAIL": {
        "in_call": "Send the caller an email they ask for during the call, from your Gmail account.",
        "post_call": "Save a follow-up email to the caller as a Gmail draft after the call (a draft for your team to review, never sent automatically).",
    },
    "TODOIST": {
        "in_call": "Create a Todoist task while talking when a follow-up is agreed.",
        "post_call": "Create a follow-up task in Todoist after the call.",
    },
    "TWILIO_SMS": {
        "in_call": "Send the caller a text message they ask for during the call.",
    },
}

# Catalog apps that exist but cannot run from a call without resource ids that
# nobody can supply today (no per-connection settings store yet).
SETUP_REQUIRED: dict[str, str] = {
    "CALCOM": "Needs a Cal.com event type to be configured before calls can book it.",
    "SLACK": "Needs a Slack channel to be configured, and the bot invited to it.",
    "DISCORD": "Needs a Discord channel to be configured.",
    "AIRTABLE": "Needs an Airtable base and table to be configured.",
    "NOTION": "Needs a Notion parent page or database to be configured.",
    "SUPABASE": "Needs a Supabase table and lookup column to be configured.",
    "ASANA": "Needs an Asana project to be configured.",
    "CLICKUP": "Needs a ClickUp list to be configured.",
    "MONDAY": "Needs a Monday.com board to be configured.",
    "MAILCHIMP": "Needs a Mailchimp audience to be configured.",
    "LINEAR": "Needs a Linear team to be configured.",
    "JIRA": "Needs a Jira project to be configured.",
    "GITHUB": "Needs a GitHub repository to be configured.",
    "SENDGRID": "Needs a verified SendGrid sender address to be configured.",
    "WHATSAPP": "Needs an approved WhatsApp message template; free-form messages are rejected after a call.",
}

# The single action the platform runs for a post-call selection when the agent
# has no explicit after-call action list for that app.
POST_CALL_DEFAULT_ACTION: dict[str, str] = {
    "TODOIST": "TODOIST_CREATE_TASK",
    "GMAIL": "GMAIL_CREATE_DRAFT",
    "HUBSPOT": "HUBSPOT_CREATE_CONTACT",
}

PLATFORM_TOOLS = frozenset({"SAVE_ENQUIRY", "CONFIRM_ORDER", "REQUEST_HUMAN_HANDOFF"})


class SelectionError(ValueError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message

    def detail(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


def _norm(app: str) -> str:
    from server.services.tool_schema_registry import _normalize

    return _normalize(str(app or ""))


def supported_modes(app: str) -> tuple[str, ...]:
    profile = CALL_INTEGRATION_PROFILES.get(_norm(app)) or {}
    return tuple(mode for mode in MODES if mode in profile)


def normalize_selection(raw: Any) -> list[dict[str, str]] | None:
    """Shape-check a client selection. ``None`` / empty means agent defaults."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise SelectionError(422, "integration_selection_invalid", "Integrations for this call must be a list.")
    if len(raw) > MAX_SELECTED:
        raise SelectionError(422, "integration_selection_invalid", f"Choose at most {MAX_SELECTED} integrations for one call.")
    out: dict[str, str] = {}
    for item in raw:
        if isinstance(item, str):
            app, mode = item, None
        elif isinstance(item, dict):
            app, mode = item.get("app") or item.get("appId") or item.get("id"), item.get("mode")
        else:
            raise SelectionError(422, "integration_selection_invalid", "Each integration must name an app and a mode.")
        if not isinstance(app, str) or not re.fullmatch(r"[A-Za-z0-9_\- ]{2,40}", app):
            raise SelectionError(422, "integration_selection_invalid", "Each integration must name an app and a mode.")
        key = _norm(app)
        modes = supported_modes(key)
        if not modes:
            reason = SETUP_REQUIRED.get(key)
            raise SelectionError(422, "integration_not_available",
                                 reason or "This integration cannot be used from calls yet.")
        if not mode:
            from server.services.tool_schema_registry import default_action_timing

            mode = default_action_timing(key) if default_action_timing(key) in modes else modes[0]
        if mode not in modes:
            raise SelectionError(422, "integration_mode_unsupported",
                                 "This integration cannot run at the chosen time. Pick during or after the call as offered.")
        if key in out and out[key] != mode:
            raise SelectionError(422, "integration_selection_invalid", "Choose one timing per integration.")
        out[key] = mode
    return [{"app": app, "mode": mode} for app, mode in out.items()] or None


async def _verified_apps(tenant_id: str, factory: Any) -> set[str]:
    from server.services.tenant_tool_cache import get_active_app_names

    return {_norm(a) for a in await get_active_app_names(str(tenant_id), factory)}


async def _agent_rules(tenant_id: str, agent_id: str, factory: Any) -> list[Any] | None:
    """Agent integration rules, or None when the agent is not this tenant's."""
    from sqlalchemy import select

    from server.db.models.entities import Agent
    from server.db.models.integration_models import AgentIntegration

    try:
        tid, aid = uuid.UUID(str(tenant_id)), uuid.UUID(str(agent_id))
    except (TypeError, ValueError):
        return None
    async with factory() as session:
        owned = (await session.execute(select(Agent.agent_id).where(
            Agent.agent_id == aid, Agent.tenant_id == tid,
        ))).scalar_one_or_none()
        if owned is None:
            return None
        return list((await session.execute(select(AgentIntegration).where(
            AgentIntegration.tenant_id == tid, AgentIntegration.agent_id == aid,
        ))).scalars().all())


def agent_allows(app: str, rules: Iterable[Any]) -> bool:
    """An app is agent-allowed unless the agent has rules for it and all are off."""
    matching = [r for r in rules if _norm(r.app_name) == app]
    return not matching or any(r.enabled for r in matching)


def agent_whitelist(app: str, rules: Iterable[Any], timing: str | None = None) -> set[str] | None:
    """Explicit per-action list from enabled agent rules, or None for all actions."""
    names: set[str] = set()
    for rule in rules:
        if _norm(rule.app_name) != app or not rule.enabled:
            continue
        if timing and rule.timing_mode != timing:
            continue
        names.update(a.upper() for a in (rule.action_whitelist or []))
    return names or None


async def validate_selection(tenant_id: str, agent_id: str, raw: Any, factory: Any = None) -> list[dict[str, str]] | None:
    """Server-side validation used by the single-call and campaign start APIs."""
    selection = normalize_selection(raw)
    if selection is None:
        return None
    if factory is None:
        from server.db.connection import get_session_factory

        factory = get_session_factory()
    if factory is None:
        raise SelectionError(503, "integration_storage_unavailable", "Integration storage is unavailable.")
    rules = await _agent_rules(tenant_id, agent_id, factory)
    if rules is None:
        raise SelectionError(404, "not_found", "Agent not found")
    verified = await _verified_apps(tenant_id, factory)
    for item in selection:
        if item["app"] not in verified:
            raise SelectionError(409, "integration_not_connected",
                                 f"{display_name(item['app'])} is not connected for this workspace. Connect it on the Integrations page first.")
        if not agent_allows(item["app"], rules):
            raise SelectionError(409, "integration_disabled_for_agent",
                                 f"{display_name(item['app'])} is turned off for this agent.")
    return selection


def display_name(app: str) -> str:
    from server.routes.integrations_catalog import CATALOG_INTEGRATIONS

    key = _norm(app)
    return next((row["name"] for row in CATALOG_INTEGRATIONS if _norm(row["id"]) == key), key.title())


async def available_for_agent(tenant_id: str, agent_id: str, factory: Any = None) -> list[dict[str, Any]]:
    """Every catalog app with what the launch flows may offer for this agent."""
    from sqlalchemy import select

    from server.db.models.integration_models import TenantIntegration
    from server.routes.integrations_catalog import CATALOG_INTEGRATIONS

    if factory is None:
        from server.db.connection import get_session_factory

        factory = get_session_factory()
    if factory is None:
        raise SelectionError(503, "integration_storage_unavailable", "Integration storage is unavailable.")
    rules = await _agent_rules(tenant_id, agent_id, factory)
    if rules is None:
        raise SelectionError(404, "not_found", "Agent not found")
    verified = await _verified_apps(tenant_id, factory)
    async with factory() as session:
        rows = (await session.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == uuid.UUID(str(tenant_id)),
            TenantIntegration.status == "ERROR",
        ))).scalars().all()
    reauth = {_norm(r.app_name) for r in rows if (r.metadata_ or {}).get("needs_reauth") is True}
    items = []
    for row in CATALOG_INTEGRATIONS:
        app = _norm(row["id"])
        profile = CALL_INTEGRATION_PROFILES.get(app) or {}
        modes = [m for m in MODES if m in profile]
        connected = app in verified
        allowed = agent_allows(app, rules)
        if not modes:
            state, reason = "setup_required", SETUP_REQUIRED.get(app, "This integration cannot be used from calls yet.")
        elif app in reauth and not connected:
            state, reason = "needs_reauth", "The connection expired. Reconnect it on the Integrations page."
        elif not connected:
            state, reason = "not_connected", "Connect it on the Integrations page first."
        elif not allowed:
            state, reason = "disabled_for_agent", "Turned off for this agent in its integration settings."
        else:
            state, reason = "available", None
        catalog_default = row.get("timing") if row.get("timing") in modes else None
        items.append({
            "app": app,
            "name": row["name"],
            "category": row.get("category"),
            "iconName": row.get("iconName"),
            "connected": connected,
            "selectable": state == "available",
            "state": state,
            "reason": reason,
            "modes": [{"mode": m, "label": "During the call" if m == "in_call" else "After the call",
                       "description": profile[m]} for m in modes],
            "defaultMode": catalog_default or (modes[0] if modes else None),
        })
    order = {"available": 0, "disabled_for_agent": 1, "needs_reauth": 2, "not_connected": 3, "setup_required": 4}
    items.sort(key=lambda i: (order[i["state"]], i["name"]))
    return items


# ---------------------------------------------------------------- runtime
_CACHE: "OrderedDict[str, tuple[float, list[dict[str, str]] | None]]" = OrderedDict()
_CACHE_TTL = 300.0
_CACHE_MAX = 1024


def _clean_runtime(raw: Any) -> list[dict[str, str]] | None:
    """Selection read back from storage: drop anything no longer supported."""
    if not isinstance(raw, list) or not raw:
        return None
    out = []
    for item in raw:
        if isinstance(item, dict):
            app, mode = _norm(item.get("app") or ""), item.get("mode")
            if mode in supported_modes(app):
                out.append({"app": app, "mode": mode})
    # A stored selection that no longer names anything usable still restricts
    # the call: it must not silently widen back to the agent defaults.
    return out


async def selection_from_meta(meta: dict[str, Any] | None, tenant_id: str | None = None) -> list[dict[str, str]] | None:
    """Resolve a call's selection from its ledger meta.

    Campaign calls always use the owning campaign's stored selection; an
    imported contact column can never inject or widen one.
    """
    meta = meta or {}
    contact = meta.get("contact") if isinstance(meta.get("contact"), dict) else {}
    campaign_id = contact.get("campaign_id") or meta.get("campaign_id")
    tenant_id = str(tenant_id or meta.get("tenant_id") or "")
    if campaign_id:
        return await campaign_selection(str(campaign_id), tenant_id)
    if "integration_selection" in meta:
        return _clean_runtime(meta.get("integration_selection"))
    return _clean_runtime(contact.get("integration_selection"))


async def campaign_selection(campaign_id: str, tenant_id: str) -> list[dict[str, str]] | None:
    from sqlalchemy import select

    from server.db.connection import get_session_factory
    from server.db.models.phase5_models import Campaign

    factory = get_session_factory()
    if factory is None:
        return None
    try:
        async with factory() as session:
            schedule = (await session.execute(select(Campaign.schedule).where(
                Campaign.campaign_id == uuid.UUID(campaign_id), Campaign.tenant_id == uuid.UUID(tenant_id),
            ))).scalar_one_or_none()
    except (ValueError, TypeError):
        return None
    if not isinstance(schedule, dict) or "integration_selection" not in schedule:
        return None
    return _clean_runtime(schedule.get("integration_selection"))


async def selection_for_call(call_id: str | None, *, tenant_id: str | None = None) -> list[dict[str, str]] | None:
    """Cached per-call lookup used on every tool listing and tool execution."""
    if not call_id:
        return None
    now = time.monotonic()
    hit = _CACHE.get(call_id)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    meta: dict[str, Any] = {}
    try:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(call_id)
        meta = dict(getattr(ctx, "meta", None) or {}) if ctx is not None else {}
        if not meta:
            from server.call.call_ledger import call_ledger

            meta = call_ledger.read_meta(call_id) or {}
    except Exception as exc:  # noqa: BLE001 - unknown calls keep the agent defaults.
        logger.debug("[CALL_INTEGRATIONS] meta unavailable: %s", type(exc).__name__)
    if tenant_id and meta.get("tenant_id") and str(meta["tenant_id"]) != str(tenant_id):
        return []  # Cross-tenant meta: expose nothing rather than the defaults.
    selection = await selection_from_meta(meta, tenant_id)
    if not meta:
        return selection  # Not written yet: do not pin the defaults for this call.
    _CACHE[call_id] = (now, selection)
    _CACHE.move_to_end(call_id)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return selection


def selected_apps(selection: list[dict[str, str]] | None, mode: str) -> set[str]:
    return {item["app"] for item in selection or [] if item.get("mode") == mode}


def filter_tools(tools: list[dict], selection: list[dict[str, str]] | None) -> list[dict]:
    """Narrow an already agent-filtered tool list to the call's in-call apps."""
    if selection is None:
        return tools
    from server.services.tool_schema_registry import tool_definition

    allowed = selected_apps(selection, "in_call")
    out = []
    for tool in tools:
        name = str(tool.get("name") or "").upper()
        if name in PLATFORM_TOOLS:
            out.append(tool)
            continue
        definition = tool_definition(name)
        if definition and definition[0] in allowed:
            out.append(tool)
    return out


def capability_rows(selection: list[dict[str, str]] | None, tools: list[dict]) -> list[str]:
    """Prompt lines naming this call's integrations (and what is not attached)."""
    if selection is None:
        return []
    from server.services.tool_schema_registry import tool_definition

    live = {tool_definition(str(t.get("name") or ""))[0] for t in tools
            if tool_definition(str(t.get("name") or "")) and str(t.get("name") or "").upper() not in PLATFORM_TOOLS}
    rows = ["call_integrations: chosen_for_this_call"]
    for item in selection:
        if item["mode"] == "in_call" and item["app"] in live:
            rows.append(f"- {display_name(item['app'])} (during the call): {CALL_INTEGRATION_PROFILES[item['app']]['in_call']}")
    after = [item["app"] for item in selection if item["mode"] == "post_call"]
    for app in after:
        rows.append(f"- {display_name(app)} (after the call, done by the platform): {CALL_INTEGRATION_PROFILES[app]['post_call']} Do not claim it is already done during the call.")
    if not live:
        rows.append("No external app can be used during this call. Do not promise to book, send, look up or create anything in another system while talking.")
    else:
        rows.append("Only the apps listed above are attached to this call. Do not offer bookings, emails, tickets or records in any other system.")
    return rows


# ------------------------------------------------------------- post-call
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def _first(facts: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = facts.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def post_call_arguments(action: str, outcome: dict[str, Any], meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Deterministic arguments for the built-in post-call actions.

    Returns None when the outcome does not hold what the action needs; the
    action is then skipped, never guessed.
    """
    facts = outcome.get("extracted_fields") if isinstance(outcome.get("extracted_fields"), dict) else {}
    contact = (meta or {}).get("contact") if isinstance((meta or {}).get("contact"), dict) else {}
    name = _first(facts, "name", "caller_name", "full_name", "customer_name") or _first(contact, "name", "first_name")
    phone = _first(facts, "phone", "callback_phone", "phone_number", "mobile") or _first(contact, "phone", "phone_e164")
    email = _first(facts, "email", "caller_email") or _first(contact, "email")
    summary = str(outcome.get("summary_en") or "").strip()
    next_action = str(outcome.get("next_action") or "").strip()
    who = name or phone or "the caller"
    if action == "TODOIST_CREATE_TASK":
        detail = next_action or summary
        if not detail:
            return None
        return {"content": f"Follow up with {who}: {detail}"[:480]}
    if action == "GMAIL_CREATE_DRAFT":
        if not email or not _EMAIL.match(email) or not summary:
            return None
        greeting = f"Hi {name.split()[0]}," if name else "Hello,"
        body = f"{greeting}\n\nThank you for speaking with us today. Here is a short recap of our call:\n\n{summary}"
        if next_action:
            body += f"\n\nNext step: {next_action}"
        return {"to": email, "subject": "Following up on our call", "body": body[:7000]}
    if action == "HUBSPOT_CREATE_CONTACT":
        if not name or not (email or phone):
            return None
        first, _, last = name.partition(" ")
        args: dict[str, Any] = {"firstname": first}
        if last:
            args["lastname"] = last
        if email and _EMAIL.match(email):
            args["email"] = email
        if phone:
            args["phone"] = phone
        return args
    return None


async def post_call_plan(selection: list[dict[str, str]], rules: list[Any]) -> list[str]:
    """Actions to run after a call that carries a selection."""
    from server.services.tool_schema_registry import tool_definition

    actions: list[str] = []
    for app in sorted(selected_apps(selection, "post_call")):
        if not agent_allows(app, rules):
            continue
        explicit = agent_whitelist(app, rules, "post_call")
        if explicit:
            actions.extend(sorted(a for a in explicit if (tool_definition(a) or ("",))[0] == app))
        elif app in POST_CALL_DEFAULT_ACTION:
            actions.append(POST_CALL_DEFAULT_ACTION[app])
    return actions


def clear_cache() -> None:
    _CACHE.clear()
