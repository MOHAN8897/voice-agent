"""
Tool Schema Registry - voice-pruned JSON schemas for each supported Nango integration.
"""
from __future__ import annotations

_SCHEMAS: dict[str, list[dict]] = {

    "GOOGLECALENDAR": [
        {
            "type": "function",
            "name": "GOOGLECALENDAR_CREATE_EVENT",
            "description": "Book a calendar appointment for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary":        {"type": "string", "description": "Event title / appointment name"},
                    "start":          {"type": "string", "description": "Start datetime ISO 8601"},
                    "end":            {"type": "string", "description": "End datetime ISO 8601"},
                    "attendee_email": {"type": "string", "description": "Caller email to invite"},
                    "description":    {"type": "string", "description": "Optional notes"},
                },
                "required": ["summary", "start", "end"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
            "description": "Find available time slots on a given date",
            "parameters": {
                "type": "object",
                "properties": {
                    "date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "duration": {"type": "integer", "description": "Duration in minutes (default 30)"},
                },
                "required": ["date"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_FIND_SLOTS",
            "description": "Find available time slots for a given day",
            "parameters": {
                "type": "object",
                "properties": {
                    "date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "duration": {"type": "integer", "description": "Duration in minutes (default 30)"},
                },
                "required": ["date"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_LIST_EVENTS",
            "description": "List upcoming calendar events for a date",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        },
    ],

    "CALENDLY": [
        {
            "type": "function",
            "name": "CALENDLY_CREATE_INVITEE",
            "description": "Schedule a Calendly meeting for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_uri": {"type": "string"},
                    "invitee_email":  {"type": "string"},
                    "invitee_name":   {"type": "string"},
                    "start_time":     {"type": "string", "description": "ISO 8601"},
                },
                "required": ["invitee_email", "start_time"],
            },
        },
        {
            "type": "function",
            "name": "CALENDLY_GET_AVAILABLE_TIMES",
            "description": "Get available slots from a Calendly event type",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_uri": {"type": "string"},
                    "start_date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date":       {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["event_type_uri", "start_date", "end_date"],
            },
        },
    ],

    "CALCOM": [
        {
            "type": "function",
            "name": "CALCOM_CREATE_BOOKING",
            "description": "Create a cal.com booking for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "integer"},
                    "start":         {"type": "string", "description": "ISO 8601"},
                    "name":          {"type": "string"},
                    "email":         {"type": "string"},
                    "notes":         {"type": "string"},
                },
                "required": ["event_type_id", "start", "name", "email"],
            },
        },
        {
            "type": "function",
            "name": "CALCOM_GET_AVAILABLE_SLOTS",
            "description": "Get available booking slots from cal.com",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "integer"},
                    "date":          {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["event_type_id", "date"],
            },
        },
    ],

    "SLACK": [
        {
            "type": "function",
            "name": "SLACK_SEND_MESSAGE",
            "description": "Send a Slack notification to a channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name or ID"},
                    "text":    {"type": "string", "description": "Message body"},
                },
                "required": ["channel", "text"],
            },
        },
    ],

    "HUBSPOT": [
        {
            "type": "function",
            "name": "HUBSPOT_CREATE_CONTACT",
            "description": "Create or update a HubSpot CRM contact",
            "parameters": {
                "type": "object",
                "properties": {
                    "firstname": {"type": "string"},
                    "lastname":  {"type": "string"},
                    "email":     {"type": "string"},
                    "phone":     {"type": "string"},
                    "company":   {"type": "string"},
                },
                "required": ["firstname"],
            },
        },
        {
            "type": "function",
            "name": "HUBSPOT_CREATE_DEAL",
            "description": "Create a new deal in HubSpot CRM",
            "parameters": {
                "type": "object",
                "properties": {
                    "dealname":  {"type": "string"},
                    "amount":    {"type": "number"},
                    "pipeline":  {"type": "string"},
                    "dealstage": {"type": "string"},
                },
                "required": ["dealname"],
            },
        },
        {
            "type": "function",
            "name": "HUBSPOT_CREATE_NOTE",
            "description": "Log a call note on a HubSpot contact or deal",
            "parameters": {
                "type": "object",
                "properties": {
                    "body":       {"type": "string"},
                    "contact_id": {"type": "string"},
                },
                "required": ["body"],
            },
        },
    ],

    "SALESFORCE": [
        {
            "type": "function",
            "name": "SALESFORCE_CREATE_LEAD",
            "description": "Create a Salesforce lead from call details",
            "parameters": {
                "type": "object",
                "properties": {
                    "FirstName":   {"type": "string"},
                    "LastName":    {"type": "string"},
                    "Email":       {"type": "string"},
                    "Phone":       {"type": "string"},
                    "Company":     {"type": "string"},
                    "Description": {"type": "string"},
                },
                "required": ["LastName", "Company"],
            },
        },
        {
            "type": "function",
            "name": "SALESFORCE_CREATE_TASK",
            "description": "Log a Salesforce follow-up task",
            "parameters": {
                "type": "object",
                "properties": {
                    "Subject":      {"type": "string"},
                    "Description":  {"type": "string"},
                    "ActivityDate": {"type": "string", "description": "YYYY-MM-DD"},
                    "WhoId":        {"type": "string"},
                },
                "required": ["Subject"],
            },
        },
    ],

    "GMAIL": [
        {
            "type": "function",
            "name": "GMAIL_SEND_EMAIL",
            "description": "Send a confirmation email to the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string"},
                    "subject": {"type": "string"},
                    "body":    {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    ],

    "OUTLOOKCALENDAR": [
        {
            "type": "function",
            "name": "OUTLOOKCALENDAR_CREATE_EVENT",
            "description": "Create an Outlook calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":   {"type": "string"},
                    "start":     {"type": "string", "description": "ISO 8601"},
                    "end":       {"type": "string", "description": "ISO 8601"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["subject", "start", "end"],
            },
        },
    ],

    "ZOOM": [
        {
            "type": "function",
            "name": "ZOOM_CREATE_MEETING",
            "description": "Schedule a Zoom meeting and return the join link",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic":      {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO 8601"},
                    "duration":   {"type": "integer", "description": "Minutes"},
                    "agenda":     {"type": "string"},
                },
                "required": ["topic", "start_time"],
            },
        },
    ],

    "NOTION": [
        {
            "type": "function",
            "name": "NOTION_CREATE_PAGE",
            "description": "Create a Notion page with call notes",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string"},
                    "title":     {"type": "string"},
                    "content":   {"type": "string"},
                },
                "required": ["parent_id", "title"],
            },
        },
    ],

    "AIRTABLE": [
        {
            "type": "function",
            "name": "AIRTABLE_CREATE_RECORD",
            "description": "Add a record to an Airtable base",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_id":    {"type": "string"},
                    "table_name": {"type": "string"},
                    "fields":     {"type": "object", "description": "Field key-value pairs"},
                },
                "required": ["base_id", "table_name", "fields"],
            },
        },
    ],

    "ZENDESK": [
        {
            "type": "function",
            "name": "ZENDESK_CREATE_TICKET",
            "description": "Create a Zendesk support ticket",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":          {"type": "string"},
                    "comment":          {"type": "string"},
                    "requester_email":  {"type": "string"},
                    "priority":         {"type": "string", "description": "low/normal/high/urgent"},
                },
                "required": ["subject", "comment"],
            },
        },
    ],

    "ASANA": [
        {
            "type": "function",
            "name": "ASANA_CREATE_TASK",
            "description": "Create an Asana task from a call action item",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":       {"type": "string"},
                    "notes":      {"type": "string"},
                    "project_id": {"type": "string"},
                    "due_on":     {"type": "string", "description": "YYYY-MM-DD"},
                    "assignee":   {"type": "string"},
                },
                "required": ["name"],
            },
        },
    ],

    "LINEAR": [
        {
            "type": "function",
            "name": "LINEAR_CREATE_ISSUE",
            "description": "Create a Linear issue from a call action item",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "team_id":     {"type": "string"},
                    "priority":    {"type": "integer", "description": "1=urgent 2=high 3=medium 4=low"},
                },
                "required": ["title", "team_id"],
            },
        },
    ],

    "JIRA": [
        {
            "type": "function",
            "name": "JIRA_CREATE_ISSUE",
            "description": "Create a Jira issue from a caller request",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "summary":     {"type": "string"},
                    "description": {"type": "string"},
                    "issue_type":  {"type": "string", "description": "Bug/Task/Story"},
                },
                "required": ["project_key", "summary"],
            },
        },
    ],

    "GITHUB": [
        {
            "type": "function",
            "name": "GITHUB_CREATE_ISSUE",
            "description": "Create a GitHub issue from a caller report",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner":  {"type": "string"},
                    "repo":   {"type": "string"},
                    "title":  {"type": "string"},
                    "body":   {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["owner", "repo", "title"],
            },
        },
    ],

    "INTERCOM": [
        {
            "type": "function",
            "name": "INTERCOM_CREATE_CONVERSATION",
            "description": "Start an Intercom conversation for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "email":   {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    ],

    "PIPEDRIVE": [
        {
            "type": "function",
            "name": "PIPEDRIVE_CREATE_PERSON",
            "description": "Create a Pipedrive contact",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":  {"type": "string"},
                    "email": {"type": "array", "items": {"type": "string"}},
                    "phone": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
        {
            "type": "function",
            "name": "PIPEDRIVE_CREATE_DEAL",
            "description": "Create a deal in Pipedrive",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":     {"type": "string"},
                    "value":     {"type": "number"},
                    "person_id": {"type": "integer"},
                    "stage_id":  {"type": "integer"},
                },
                "required": ["title"],
            },
        },
    ],

    "SHOPIFY": [
        {
            "type": "function",
            "name": "SHOPIFY_GET_ORDER",
            "description": "Look up a Shopify order by ID or email",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "email":    {"type": "string"},
                },
            },
        },
    ],

    "STRIPE": [
        {
            "type": "function",
            "name": "STRIPE_CREATE_PAYMENT_LINK",
            "description": "Generate a Stripe payment link for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "price_id": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "email":    {"type": "string"},
                },
                "required": ["price_id"],
            },
        },
    ],

    "TWILIO_SMS": [
        {
            "type": "function",
            "name": "TWILIO_SMS_SEND_MESSAGE",
            "description": "Send an SMS to the caller's phone",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":   {"type": "string", "description": "E.164 phone number"},
                    "body": {"type": "string"},
                },
                "required": ["to", "body"],
            },
        },
    ],

    "MICROSOFTTEAMS": [
        {
            "type": "function",
            "name": "MICROSOFTTEAMS_SEND_MESSAGE",
            "description": "Post a message to a Microsoft Teams channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "message":    {"type": "string"},
                },
                "required": ["channel_id", "message"],
            },
        },
    ],

    "CLICKUP": [
        {
            "type": "function",
            "name": "CLICKUP_CREATE_TASK",
            "description": "Create a ClickUp task from a caller action item",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id":     {"type": "string"},
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "priority":    {"type": "integer", "description": "1=urgent 2=high 3=normal 4=low"},
                },
                "required": ["list_id", "name"],
            },
        },
    ],

    "TWILIO_SMS": [
        {
            "type": "function",
            "name": "TWILIO_SMS_SEND_MESSAGE",
            "description": "Send an SMS to the caller's phone",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":   {"type": "string", "description": "E.164 phone number"},
                    "body": {"type": "string"},
                },
                "required": ["to", "body"],
            },
        },
    ],

    "SENDGRID": [
        {
            "type": "function",
            "name": "SENDGRID_SEND_EMAIL",
            "description": "Send a transactional email via SendGrid",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string"},
                    "subject": {"type": "string"},
                    "body":    {"type": "string"},
                    "from_email": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    ],

    "MAILCHIMP": [
        {
            "type": "function",
            "name": "MAILCHIMP_ADD_SUBSCRIBER",
            "description": "Add caller to a Mailchimp audience list",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id":    {"type": "string"},
                    "email":      {"type": "string"},
                    "first_name": {"type": "string"},
                    "last_name":  {"type": "string"},
                },
                "required": ["list_id", "email"],
            },
        },
    ],

    "TRELLO": [
        {
            "type": "function",
            "name": "TRELLO_CREATE_CARD",
            "description": "Add a Trello card for a caller follow-up",
            "parameters": {
                "type": "object",
                "properties": {
                    "idList": {"type": "string"},
                    "name":   {"type": "string"},
                    "desc":   {"type": "string"},
                    "due":    {"type": "string", "description": "ISO 8601 due date"},
                },
                "required": ["idList", "name"],
            },
        },
    ],

    "FRESHDESK": [
        {
            "type": "function",
            "name": "FRESHDESK_LOOKUP_TICKET",
            "description": "Lookup customer support ticket by ID or email",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "email":     {"type": "string"},
                },
            },
        },
        {
            "type": "function",
            "name": "FRESHDESK_CREATE_TICKET",
            "description": "Create a Freshdesk customer support ticket",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":     {"type": "string"},
                    "description": {"type": "string"},
                    "email":       {"type": "string"},
                    "priority":    {"type": "integer", "description": "1=low 2=medium 3=high 4=urgent"},
                },
                "required": ["subject", "description"],
            },
        },
    ],

    "WOOCOMMERCE": [
        {
            "type": "function",
            "name": "WOOCOMMERCE_GET_ORDER",
            "description": "Lookup WooCommerce order by order ID or email",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "email":    {"type": "string"},
                },
            },
        },
        {
            "type": "function",
            "name": "WOOCOMMERCE_CHECK_STOCK",
            "description": "Check product stock inventory by product ID or SKU",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "sku":        {"type": "string"},
                },
            },
        },
    ],

    "WHATSAPP": [
        {
            "type": "function",
            "name": "WHATSAPP_SEND_MESSAGE",
            "description": "Send a WhatsApp message or confirmation to the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string", "description": "E.164 phone number"},
                    "message": {"type": "string"},
                },
                "required": ["to", "message"],
            },
        },
    ],

    "DISCORD": [
        {
            "type": "function",
            "name": "DISCORD_SEND_MESSAGE",
            "description": "Post a message or lead summary to a Discord channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "content":    {"type": "string"},
                },
                "required": ["content"],
            },
        },
    ],

    "SUPABASE": [
        {
            "type": "function",
            "name": "SUPABASE_INSERT_ROW",
            "description": "Insert a record into a Supabase database table",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "row":   {"type": "object", "description": "Row key-values"},
                },
                "required": ["table", "row"],
            },
        },
        {
            "type": "function",
            "name": "SUPABASE_QUERY_ROW",
            "description": "Query a record from a Supabase table by column filter",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":         {"type": "string"},
                    "filter_column": {"type": "string"},
                    "filter_value":  {"type": "string"},
                },
                "required": ["table", "filter_column", "filter_value"],
            },
        },
    ],

    "MONDAY": [
        {
            "type": "function",
            "name": "MONDAY_CREATE_ITEM",
            "description": "Create an action item or lead on a Monday.com board",
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id":       {"type": "string"},
                    "item_name":      {"type": "string"},
                    "column_values":  {"type": "object"},
                },
                "required": ["item_name"],
            },
        },
    ],

    "TODOIST": [
        {
            "type": "function",
            "name": "TODOIST_CREATE_TASK",
            "description": "Create a Todoist follow-up task or reminder",
            "parameters": {
                "type": "object",
                "properties": {
                    "content":    {"type": "string"},
                    "due_string": {"type": "string"},
                    "priority":   {"type": "integer", "description": "1=normal 4=urgent"},
                },
                "required": ["content"],
            },
        },
    ],
}

VOICE_RESPONSE_KEYS: dict[str, tuple] = {
    "GOOGLECALENDAR":   ("status", "confirmed", "date", "time", "summary", "event_id", "slots", "available"),
    "CALENDLY":         ("status", "booking_url", "start_time", "summary"),
    "CALCOM":           ("status", "uid", "start_time", "summary"),
    "SLACK":            ("status", "message_id", "channel", "summary"),
    "HUBSPOT":          ("status", "id", "contact_id", "deal_id", "summary"),
    "SALESFORCE":       ("status", "id", "lead_id", "task_id", "summary"),
    "GMAIL":            ("status", "message_id", "summary"),
    "OUTLOOKCALENDAR":  ("status", "event_id", "date", "time", "summary"),
    "ZOOM":             ("status", "join_url", "start_time", "topic", "summary"),
    "NOTION":           ("status", "page_id", "url", "summary"),
    "AIRTABLE":         ("status", "record_id", "summary"),
    "ZENDESK":          ("status", "ticket_id", "ticket_url", "summary"),
    "ASANA":            ("status", "task_id", "due_on", "summary"),
    "LINEAR":           ("status", "issue_id", "identifier", "summary"),
    "JIRA":             ("status", "issue_id", "key", "summary"),
    "GITHUB":           ("status", "issue_number", "html_url", "summary"),
    "INTERCOM":         ("status", "conversation_id", "summary"),
    "PIPEDRIVE":        ("status", "id", "summary"),
    "SHOPIFY":          ("status", "order_id", "name", "financial_status", "summary"),
    "STRIPE":           ("status", "url", "payment_link_id", "summary"),
    "TWILIO_SMS":       ("status", "message_sid", "summary"),
    "MICROSOFTTEAMS":   ("status", "message_id", "summary"),
    "CLICKUP":          ("status", "task_id", "url", "summary"),
    "TRELLO":           ("status", "card_id", "url", "summary"),
    "SENDGRID":         ("status", "message_id", "summary"),
    "MAILCHIMP":        ("status", "subscriber_id", "summary"),
    "FRESHDESK":        ("status", "ticket_id", "subject", "priority", "summary"),
    "WOOCOMMERCE":      ("status", "order_id", "total", "shipping_status", "stock", "summary"),
    "WHATSAPP":         ("status", "message_id", "summary"),
    "DISCORD":          ("status", "message_id", "summary"),
    "SUPABASE":         ("status", "data", "summary"),
    "MONDAY":           ("status", "item_id", "summary"),
    "TODOIST":          ("status", "task_id", "content", "summary"),
}


def _normalize(app_name: str) -> str:
    clean = app_name.strip().upper().replace("-", "_").replace(" ", "_")
    if clean in _SCHEMAS:
        return clean
    stripped = clean.replace("_", "")
    if stripped in _SCHEMAS:
        return stripped
    return clean


def get_tools_for_tenant(active_app_names: list[str]) -> list[dict]:
    """Return voice-pruned tool schemas for ONLY the tenant's active integrations."""
    schemas: list[dict] = []
    seen: set[str] = set()
    for raw_name in active_app_names:
        key = _normalize(raw_name)
        for schema in _SCHEMAS.get(key, []):
            tool_name = schema.get("name", "")
            if tool_name and tool_name not in seen:
                seen.add(tool_name)
                schemas.append(schema)
    return schemas


def get_tool_names_for_tenant(active_app_names: list[str]) -> set[str]:
    """Return exact tool name strings, canonical app keys, and common action suffixes for dispatch filtering."""
    names: set[str] = set()
    for raw_name in active_app_names:
        key = _normalize(raw_name)
        clean = key.lower().replace("-", "_")
        names.add(key)
        names.add(clean)
        names.add(raw_name)
        names.add(raw_name.lower())
        # Add common action suffixes for dispatch filter compatibility
        for suffix in (
            "create_event", "find_slots", "find_free_slots", "list_events",
            "send_message", "search", "create_lead", "create_contact", "action"
        ):
            names.add(f"{clean}_{suffix}")
            names.add(f"{key}_{suffix.upper()}")
        for schema in _SCHEMAS.get(key, []):
            tool_name = schema.get("name", "")
            if tool_name:
                names.add(tool_name)
                names.add(tool_name.lower())
    return names


def get_response_keys_for_tool(tool_name: str) -> tuple:
    """Return response key whitelist for a given tool (for sanitize_voice_response)."""
    upper = tool_name.upper()
    for app_key, keys in VOICE_RESPONSE_KEYS.items():
        if upper.startswith(app_key) or upper.startswith(app_key.replace("_", "")):
            return keys
    return ("status", "summary")


def list_supported_apps() -> list[str]:
    return sorted(_SCHEMAS.keys())
