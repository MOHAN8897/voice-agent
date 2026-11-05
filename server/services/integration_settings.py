"""Per-connection setup for integrations whose actions need a fixed resource.

A Slack channel, a Notion parent page or a Cal.com event type is chosen once by
the tenant on the Integrations page, not guessed by the model mid-call. The
values live in ``tenant_integrations.metadata.settings`` and are:

* stripped from the tool schema the model sees (it cannot invent them), and
* merged into the action arguments by the server before validation.

An app whose required settings are missing is ``setup_required``: it is never
offered to a call, so it cannot fail after the caller was told it is done.
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from server.utils.logger import logger

# field -> label, help, required, and which action parameter it fills.
# ``resource`` names a lister in :func:`list_resources` that offers choices.
APP_SETTINGS: dict[str, list[dict[str, Any]]] = {
    "SLACK": [{"key": "channel", "label": "Channel", "required": True, "resource": "slack_channels",
               "help": "The channel the agent posts to. Invite the app to a private channel first.",
               "fills": {"SLACK_SEND_MESSAGE": "channel"}}],
    "DISCORD": [{"key": "channel_id", "label": "Channel ID", "required": True,
                 "help": "Right-click the channel in Discord (Developer Mode on) and copy its ID. The bot must be in the server.",
                 "fills": {"DISCORD_SEND_MESSAGE": "channel_id"}}],
    "AIRTABLE": [{"key": "base_id", "label": "Base", "required": True, "resource": "airtable_bases",
                  "fills": {"AIRTABLE_CREATE_RECORD": "base_id", "AIRTABLE_SEARCH_RECORDS": "base_id"}},
                 {"key": "table_name", "label": "Table", "required": True,
                  "help": "After-call records fill the columns Name, Phone, Email and Summary when they exist.",
                  "fills": {"AIRTABLE_CREATE_RECORD": "table_name", "AIRTABLE_SEARCH_RECORDS": "table_name"}}],
    "GOOGLESHEETS": [{"key": "spreadsheet_id", "label": "Spreadsheet link", "required": True,
                      "help": "Paste the sheet's address from your browser. It must be in the Google account you connected.",
                      "fills": {"GOOGLESHEETS_FIND_ROWS": "spreadsheet_id", "GOOGLESHEETS_ADD_ROW": "spreadsheet_id"}},
                     {"key": "sheet_name", "label": "Tab", "required": True, "resource": "sheets_tabs",
                      "help": "Row 1 must hold the column headings. After-call rows fill Name, Phone, Email, Summary, Next step and Date when those headings exist.",
                      "fills": {"GOOGLESHEETS_FIND_ROWS": "sheet_name", "GOOGLESHEETS_ADD_ROW": "sheet_name"}},
                     {"key": "lookup_heading", "label": "Look callers up by", "required": False,
                      "help": "The heading the agent searches during a call, for example Phone or Order ID. Leave empty to only add rows.",
                      "fills": {"GOOGLESHEETS_FIND_ROWS": "lookup_column"}}],
    "NOTION": [{"key": "parent_id", "label": "Parent page or database", "required": True, "resource": "notion_parents",
                "help": "Share that page or database with the integration in Notion first.",
                "fills": {"NOTION_CREATE_PAGE": "parent_id"}}],
    "SUPABASE": [{"key": "table", "label": "Table", "required": True,
                  "fills": {"SUPABASE_INSERT_ROW": "table", "SUPABASE_QUERY_ROW": "table"}},
                 {"key": "lookup_column", "label": "Lookup column", "required": True,
                  "help": "The column the agent searches by, for example phone or order_id.",
                  "fills": {"SUPABASE_QUERY_ROW": "filter_column"}}],
    "ASANA": [{"key": "project_id", "label": "Project", "required": True, "resource": "asana_projects",
               "fills": {"ASANA_CREATE_TASK": "project_id"}}],
    "CLICKUP": [{"key": "list_id", "label": "List ID", "required": True,
                 "help": "Open the list in ClickUp; the ID is the number after /li/ in the address.",
                 "fills": {"CLICKUP_CREATE_TASK": "list_id"}}],
    "MONDAY": [{"key": "board_id", "label": "Board", "required": True, "resource": "monday_boards",
                "fills": {"MONDAY_CREATE_ITEM": "board_id"}}],
    "MAILCHIMP": [{"key": "list_id", "label": "Audience", "required": True, "resource": "mailchimp_lists",
                   "fills": {"MAILCHIMP_ADD_SUBSCRIBER": "list_id"}}],
    "LINEAR": [{"key": "team_id", "label": "Team", "required": True, "resource": "linear_teams",
                "fills": {"LINEAR_CREATE_ISSUE": "team_id"}}],
    "JIRA": [{"key": "project_key", "label": "Project", "required": True, "resource": "jira_projects",
              "fills": {"JIRA_CREATE_ISSUE": "project_key"}}],
    "GITHUB": [{"key": "repository", "label": "Repository (owner/name)", "required": True, "resource": "github_repos",
                "fills": {}}],
    "SENDGRID": [{"key": "from_email", "label": "Verified sender address", "required": True,
                  "help": "Must be a verified Single Sender or on an authenticated domain in SendGrid.",
                  "fills": {"SENDGRID_SEND_EMAIL": "from_email"}}],
    "WHATSAPP": [{"key": "phone_number_id", "label": "Phone number ID", "required": True,
                  "help": "WhatsApp Manager > Phone numbers.", "fills": {"WHATSAPP_SEND_MESSAGE": "phone_number_id"}},
                 {"key": "template_name", "label": "Approved template name", "required": True,
                  "help": "A Utility template whose body has one {{1}} variable for the message text.",
                  "fills": {"WHATSAPP_SEND_MESSAGE": "template_name"}},
                 {"key": "template_language", "label": "Template language code", "required": True,
                  "help": "For example en or en_US, exactly as approved.",
                  "fills": {"WHATSAPP_SEND_MESSAGE": "template_language"}}],
    "CALCOM": [{"key": "event_type_id", "label": "Event type", "required": True, "resource": "calcom_event_types",
                "fills": {"CALCOM_CREATE_BOOKING": "event_type_id", "CALCOM_GET_AVAILABLE_SLOTS": "event_type_id"}}],
    "HUBSPOT": [{"key": "pipeline", "label": "Deal pipeline", "required": False, "resource": "hubspot_pipelines",
                 "help": "Needed only for creating deals.", "fills": {"HUBSPOT_CREATE_DEAL": "pipeline"}},
                {"key": "dealstage", "label": "New deal stage", "required": False, "resource": "hubspot_stages",
                 "fills": {"HUBSPOT_CREATE_DEAL": "dealstage"}}],
    # How the business's emails look and whether a person reviews them first. All
    # optional: without them the agent writes and sends the email itself.
    "GMAIL": [{"key": "send_mode", "label": "Before an email goes out", "required": False,
               "choices": [{"value": "send", "label": "Send it right away"},
                           {"value": "draft", "label": "Save it as a draft for me to review"}],
               "help": "For emails the agent sends during a call. With drafts, the email waits in your Gmail Drafts and "
                       "nothing reaches the customer until you press Send; the agent tells the caller your team will email "
                       "them. After-call follow-ups are always saved as drafts for you to review.",
               "fills": {}},
              {"key": "subject_prefix", "label": "Subject starts with", "required": False, "max_length": 60,
               "help": "For example your business name. Put before the subject the agent writes.",
               "fills": {}},
              {"key": "signature", "label": "Signature", "required": False, "multiline": True, "max_length": 600,
               "help": "Added to the end of every email, for example your name, business and phone number.",
               "fills": {}}],
    "GOOGLECALENDAR": [{"key": "day_start", "label": "Bookable from", "required": False,
                        "help": "Earliest appointment time, HH:MM in the calendar's time zone (default 09:00).",
                        "fills": {"GOOGLECALENDAR_FIND_FREE_SLOTS": "day_start"}},
                       {"key": "day_end", "label": "Bookable until", "required": False,
                        "help": "Latest appointment end, HH:MM (default 17:00).",
                        "fills": {"GOOGLECALENDAR_FIND_FREE_SLOTS": "day_end"}}],
}

# GitHub's single "owner/name" setting fills two parameters.
_SPLIT_FILLS = {"GITHUB": {"repository": {"GITHUB_CREATE_ISSUE": ("owner", "repo"), "GITHUB_SEARCH_ISSUES": ("owner", "repo")}}}

_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def _norm(app: str) -> str:
    from server.services.tool_schema_registry import _normalize

    return _normalize(str(app or ""))


def spec_for(app: str) -> list[dict[str, Any]]:
    return APP_SETTINGS.get(_norm(app), [])


def missing_required(app: str, settings: dict[str, Any] | None) -> list[str]:
    values = settings or {}
    return [f["label"] for f in spec_for(app) if f.get("required") and not str(values.get(f["key"]) or "").strip()]


def is_configured(app: str, settings: dict[str, Any] | None) -> bool:
    return not missing_required(app, settings)


def spreadsheet_id(value: str) -> str:
    """The ID from a Google Sheets link, or the ID itself; "" when it is neither."""
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,100})", value)
    candidate = match.group(1) if match else value.strip()
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{20,100}", candidate) else ""


def clean_settings(app: str, raw: Any) -> dict[str, str]:
    """Validate a tenant's submitted settings; unknown keys are dropped."""
    if not isinstance(raw, dict):
        raise ValueError("Settings must be an object.")
    out: dict[str, str] = {}
    for field in spec_for(app):
        value = str(raw.get(field["key"]) or "").strip()
        if not value:
            continue
        multiline = bool(field.get("multiline"))
        if multiline:
            value = "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").split("\n"))
        allowed_control = {"\n"} if multiline else set()
        if len(value) > int(field.get("max_length") or 255) or any(ord(c) < 32 and c not in allowed_control for c in value):
            raise ValueError(f"{field['label']} is not valid.")
        choices = field.get("choices")
        if choices and value not in {c["value"] for c in choices}:
            raise ValueError(f"Choose an option for {field['label']}.")
        key = field["key"]
        if key in {"day_start", "day_end"} and not _TIME.match(value):
            raise ValueError(f"{field['label']} must look like 09:30.")
        if key == "from_email" and not _EMAIL.match(value):
            raise ValueError("Enter a valid sender email address.")
        if key == "repository" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", value):
            raise ValueError("Enter the repository as owner/name.")
        if key == "event_type_id" and not value.isdigit():
            raise ValueError("Choose a Cal.com event type.")
        if key == "lookup_column" and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
            raise ValueError("Enter a column name using letters, digits and underscores.")
        if key == "spreadsheet_id":
            value = spreadsheet_id(value)
            if not value:
                raise ValueError("Paste the Google Sheet's link (docs.google.com/spreadsheets/d/...).")
        out[key] = value
    if out.get("day_start") and out.get("day_end") and out["day_start"] >= out["day_end"]:
        raise ValueError("Bookable until must be later than bookable from.")
    return out


def filled_params(app: str, action: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    """Action arguments supplied by the tenant's setup (never by the model)."""
    values = settings or {}
    app, action = _norm(app), action.upper()
    out: dict[str, Any] = {}
    for field in spec_for(app):
        param = field.get("fills", {}).get(action)
        value = str(values.get(field["key"]) or "").strip()
        if param and value:
            out[param] = int(value) if param == "event_type_id" else value
        split = _SPLIT_FILLS.get(app, {}).get(field["key"], {}).get(action)
        if split and "/" in value:
            out.update(dict(zip(split, value.split("/", 1))))
    return out


def setting_params(action: str) -> set[str]:
    """Every parameter of ``action`` that tenant setup owns (configured or not)."""
    from server.services.tool_schema_registry import tool_definition

    definition = tool_definition(action)
    if not definition:
        return set()
    app, action = definition[0], action.upper()
    names = {f["fills"][action] for f in spec_for(app) if action in f.get("fills", {})}
    for split in _SPLIT_FILLS.get(app, {}).values():
        names.update(split.get(action, ()))
    return names


def model_facing_schema(tool: dict) -> dict:
    """The tool as the model sees it: setup-owned parameters removed."""
    hidden = setting_params(str(tool.get("name") or ""))
    if not hidden:
        return tool
    out = copy.deepcopy(tool)
    params = out.get("parameters") or {}
    for name in hidden:
        (params.get("properties") or {}).pop(name, None)
    if "required" in params:
        params["required"] = [r for r in params["required"] if r not in hidden]
    return out


async def tenant_settings(tenant_id: str, factory: Any = None) -> dict[str, dict[str, str]]:
    """Every verified app's saved setup for a tenant, keyed by normalized app."""
    from sqlalchemy import select

    from server.db.models.integration_models import TenantIntegration

    if factory is None:
        from server.db.connection import get_session_factory

        factory = get_session_factory()
    if factory is None:
        return {}
    try:
        async with factory() as session:
            rows = (await session.execute(select(TenantIntegration).where(
                TenantIntegration.tenant_id == uuid.UUID(str(tenant_id)),
                TenantIntegration.status == "ACTIVE",
            ))).scalars().all()
    except Exception as exc:  # noqa: BLE001 - missing setup keeps the app unavailable
        logger.warning("[INTEGRATION_SETTINGS] read failed: %s", type(exc).__name__)
        return {}
    return {_norm(r.app_name): dict((r.metadata_ or {}).get("settings") or {}) for r in rows}


# ------------------------------------------------------------ resource pickers
async def list_resources(resource: str, client: Any, base: str, headers: dict, settings: dict[str, Any]) -> list[dict[str, str]]:
    """Choices for a setup field, read live through the tenant's own connection."""
    root = f"{base}/proxy"

    async def get(path: str, **kw: Any) -> Any:
        response = await client.get(f"{root}{path}", headers=headers, **kw)
        response.raise_for_status()
        return response.json()

    if resource == "slack_channels":
        data = await get("/conversations.list", params={"types": "public_channel,private_channel", "exclude_archived": "true", "limit": 200})
        if not data.get("ok"):
            raise ValueError(str(data.get("error") or "slack_error"))
        return [{"value": c["id"], "label": f"#{c.get('name')}"} for c in data.get("channels", []) if c.get("id")]
    if resource == "sheets_tabs":
        sheet = spreadsheet_id(str(settings.get("spreadsheet_id") or ""))
        if not sheet:
            raise ValueError("spreadsheet_required")
        data = await get(f"/v4/spreadsheets/{sheet}", params={"fields": "sheets.properties.title"})
        return [{"value": s["properties"]["title"], "label": s["properties"]["title"]}
                for s in data.get("sheets", []) if (s.get("properties") or {}).get("title")]
    if resource == "airtable_bases":
        data = await get("/v0/meta/bases")
        return [{"value": b["id"], "label": b.get("name") or b["id"]} for b in data.get("bases", [])]
    if resource == "notion_parents":
        response = await client.post(f"{root}/v1/search", headers={**headers, "Notion-Version": "2022-06-28"}, json={"page_size": 50})
        response.raise_for_status()
        out = []
        for item in response.json().get("results", []):
            title = ""
            if item.get("object") == "database":
                title = "".join(t.get("plain_text", "") for t in item.get("title", []))
            else:
                for prop in (item.get("properties") or {}).values():
                    if prop.get("type") == "title":
                        title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
            out.append({"value": item["id"], "label": f"{title or 'Untitled'} ({item.get('object')})"})
        return out
    if resource == "asana_projects":
        data = await get("/api/1.0/projects", params={"limit": 100, "archived": "false"})
        return [{"value": p["gid"], "label": p.get("name") or p["gid"]} for p in data.get("data", [])]
    if resource == "monday_boards":
        response = await client.post(f"{root}/v2", headers=headers, json={"query": "{ boards(limit: 100) { id name } }"})
        response.raise_for_status()
        return [{"value": str(b["id"]), "label": b.get("name") or str(b["id"])} for b in (response.json().get("data") or {}).get("boards", [])]
    if resource == "mailchimp_lists":
        data = await get("/3.0/lists", params={"count": 100, "fields": "lists.id,lists.name"})
        return [{"value": l["id"], "label": l.get("name") or l["id"]} for l in data.get("lists", [])]
    if resource == "linear_teams":
        response = await client.post(f"{root}/graphql", headers=headers, json={"query": "{ teams(first: 100) { nodes { id name key } } }"})
        response.raise_for_status()
        nodes = ((response.json().get("data") or {}).get("teams") or {}).get("nodes", [])
        return [{"value": t["id"], "label": f"{t.get('name')} ({t.get('key')})"} for t in nodes]
    if resource == "jira_projects":
        from server.services.nango_service import jira_api_root

        jira_root = await jira_api_root(client, base, headers)
        response = await client.get(f"{jira_root}/rest/api/3/project/search", headers=headers, params={"maxResults": 100})
        response.raise_for_status()
        return [{"value": p["key"], "label": f"{p.get('name')} ({p['key']})"} for p in response.json().get("values", [])]
    if resource == "github_repos":
        data = await get("/user/repos", params={"per_page": 100, "sort": "updated"})
        return [{"value": r["full_name"], "label": r["full_name"]} for r in data if isinstance(r, dict) and r.get("full_name")]
    if resource == "calcom_event_types":
        data = await get("/event-types", headers={**headers, "cal-api-version": "2024-06-14"})
        items = data.get("data") if isinstance(data.get("data"), list) else []
        return [{"value": str(e["id"]), "label": f"{e.get('title')} ({e.get('lengthInMinutes') or e.get('length')} min)"} for e in items if e.get("id")]
    if resource == "hubspot_pipelines":
        data = await get("/crm/v3/pipelines/deals")
        return [{"value": p["id"], "label": p.get("label") or p["id"]} for p in data.get("results", [])]
    if resource == "hubspot_stages":
        data = await get("/crm/v3/pipelines/deals")
        pipeline = str(settings.get("pipeline") or "")
        return [{"value": s["id"], "label": f"{p.get('label')}: {s.get('label')}"}
                for p in data.get("results", []) if not pipeline or p.get("id") == pipeline for s in p.get("stages", [])]
    raise ValueError("Unknown resource")


def apply_email_format(tool_name: str, arguments: dict[str, Any], saved: dict[str, Any] | None) -> tuple[str, dict[str, Any], bool]:
    """The business's own email format, applied by the server (never left to the model).

    Returns the action to run, its arguments, and whether the email was held as a
    draft for review instead of being sent.
    """
    name = str(tool_name or "").upper()
    if name not in {"GMAIL_SEND_EMAIL", "GMAIL_CREATE_DRAFT"}:
        return tool_name, arguments, False
    settings = saved or {}
    args = dict(arguments)
    prefix = str(settings.get("subject_prefix") or "").strip()
    subject = str(args.get("subject") or "").strip()
    if prefix and not subject.casefold().startswith(prefix.casefold()):
        args["subject"] = f"{prefix} — {subject}" if subject else prefix
    signature = str(settings.get("signature") or "").strip()
    body = str(args.get("body") or "").rstrip()
    if signature and signature not in body:
        args["body"] = f"{body}\n\n{signature}" if body else signature
    held = name == "GMAIL_SEND_EMAIL" and str(settings.get("send_mode") or "send") == "draft"
    return ("GMAIL_CREATE_DRAFT" if held else tool_name), args, held


def open_link(app: str, settings: dict[str, Any] | None) -> dict[str, str] | None:
    """Where the business can see what its agents wrote, in the app itself.

    Built only from the workspace's own saved setup (never from caller data), and
    only for addresses the provider documents as stable.
    """
    name, values = _norm(app), settings or {}
    if name == "GOOGLESHEETS":
        sheet = spreadsheet_id(str(values.get("spreadsheet_id") or ""))
        if not sheet:
            return None
        return {"url": f"https://docs.google.com/spreadsheets/d/{sheet}/edit", "label": "Open sheet"}
    if name == "GMAIL":
        if str(values.get("send_mode") or "send") == "draft":
            return {"url": "https://mail.google.com/mail/#drafts", "label": "Open Gmail drafts"}
        return {"url": "https://mail.google.com/mail/#sent", "label": "Open sent emails"}
    if name == "GOOGLECALENDAR":
        return {"url": "https://calendar.google.com/calendar/r", "label": "Open calendar"}
    return None

