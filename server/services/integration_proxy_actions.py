"""Additional catalog actions executed through the tenant's authenticated proxy."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from server.services.integration_safety import path_segment

EXTENDED_ACTIONS = frozenset({
    "CALENDLY_CREATE_INVITEE", "CALENDLY_GET_AVAILABLE_TIMES", "SALESFORCE_CREATE_TASK",
    "AIRTABLE_CREATE_RECORD", "LINEAR_CREATE_ISSUE", "JIRA_CREATE_ISSUE",
    "INTERCOM_CREATE_CONVERSATION", "PIPEDRIVE_CREATE_PERSON", "PIPEDRIVE_CREATE_DEAL",
    "MICROSOFTTEAMS_SEND_MESSAGE", "TRELLO_CREATE_CARD",
})


async def execute_extended_action(client: httpx.AsyncClient, base: str, headers: dict, action: str, params: dict) -> dict:
    root = f"{base}/proxy"
    endpoint: str
    payload: dict
    result_key = "id"
    if action.startswith("CALENDLY_"):
        event_type = str(params.get("event_type_uri") or "")
        uri = urlsplit(event_type)
        if uri.scheme != "https" or uri.netloc != "api.calendly.com" or not uri.path.startswith("/event_types/"):
            return {"status": "error", "message": "Select a valid event type from the connected calendar."}
        if action == "CALENDLY_GET_AVAILABLE_TIMES":
            start = datetime.combine(date.fromisoformat(params["start_date"]), time.min, timezone.utc)
            end = datetime.combine(date.fromisoformat(params["end_date"]), time.min, timezone.utc) + timedelta(days=1)
            # Calendly needs a future start_time and a window of at most 7 days.
            start = max(start, datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=1))
            if end <= start or end - start > timedelta(days=7):
                return {"status": "error", "message": "Choose an availability window of at most 7 days, starting from today or later."}
            response = await client.get(f"{root}/event_type_available_times", headers=headers, params={
                "event_type": event_type, "start_time": start.isoformat(), "end_time": end.isoformat(),
            })
            response.raise_for_status()
            data = response.json()
            if not isinstance(data.get("collection"), list):
                return {"status": "error", "message": "Calendar availability could not be verified."}
            slots = [item["start_time"] for item in data["collection"][:10] if item.get("status") == "available" and item.get("start_time")]
            return {"status": "available" if slots else "unavailable", "slots": slots, "summary": "Availability returned by the calendar."}
        start = datetime.fromisoformat(params["start_time"].replace("Z", "+00:00"))
        if start.tzinfo is None or start <= datetime.now(timezone.utc):
            return {"status": "error", "message": "Choose a future time with its timezone."}
        invitee = {"email": params["invitee_email"], "timezone": params["time_zone"]}
        if params.get("invitee_name"):
            invitee["name"] = params["invitee_name"]
        response = await client.post(f"{root}/invitees", headers=headers, json={
            "event_type": event_type, "start_time": start.astimezone(timezone.utc).isoformat(), "invitee": invitee,
        })
        response.raise_for_status()
        resource = response.json().get("resource") or {}
        if not resource.get("uri") or resource.get("status") != "active":
            return {"status": "unknown", "message": "The booking could not be confirmed. Check the calendar before retrying."}
        return {"status": "success", "confirmed": True, "event_uri": resource.get("event"), "invitee_uri": resource["uri"], "summary": "Calendar booking confirmed."}
    if action == "SALESFORCE_CREATE_TASK":
        endpoint, payload, result_key = "/services/data/v57.0/sobjects/Task", params, "task_id"
    elif action == "AIRTABLE_CREATE_RECORD":
        endpoint = f"/v0/{path_segment(params['base_id'])}/{path_segment(params['table_name'])}"
        payload, result_key = {"fields": params["fields"]}, "record_id"
    elif action == "LINEAR_CREATE_ISSUE":
        payload = {"query": "mutation CreateIssue($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier } } }",
                   "variables": {"input": {"teamId": params["team_id"], "title": params["title"], **{k: params[k] for k in ("description", "priority") if k in params}}}}
        response = await client.post(f"{root}/graphql", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        created = data.get("data", {}).get("issueCreate") or {}
        if data.get("errors") or created.get("success") is not True or not created.get("issue", {}).get("id"):
            return {"status": "error", "message": "Issue creation was not confirmed."}
        return {"status": "success", "issue_id": created["issue"]["id"], "identifier": created["issue"].get("identifier"), "summary": "Issue created."}
    elif action == "JIRA_CREATE_ISSUE":
        fields = {"project": {"key": params["project_key"]}, "summary": params["summary"], "issuetype": {"name": params.get("issue_type") or "Task"}}
        if params.get("description"):
            fields["description"] = {"version": 1, "type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": params["description"]}]}]}
        from server.services.nango_service import jira_api_root

        jira_root = await jira_api_root(client, base, headers)
        endpoint, payload, result_key = jira_root[len(root):] + "/rest/api/3/issue", {"fields": fields}, "issue_id"
    elif action == "INTERCOM_CREATE_CONVERSATION":
        contact_id = params.get("contact_id")
        if not contact_id:
            response = await client.post(f"{root}/contacts/search", headers=headers, json={"query": {"field": "email", "operator": "=", "value": params["email"]}})
            response.raise_for_status()
            contacts = response.json().get("data") or []
            if len(contacts) != 1 or not contacts[0].get("id"):
                return {"status": "error", "message": "A unique existing contact is required before creating a conversation."}
            contact_id = contacts[0]["id"]
        endpoint, payload, result_key = "/conversations", {"from": {"type": "contact", "id": contact_id}, "body": params["message"]}, "conversation_id"
    elif action == "PIPEDRIVE_CREATE_PERSON":
        payload = {"name": params["name"]}
        for source, target in (("email", "emails"), ("phone", "phones")):
            if params.get(source):
                payload[target] = [{"value": value, "primary": index == 0} for index, value in enumerate(params[source])]
        endpoint = "/v2/persons"  # Nango base_url is {api_domain}/api
    elif action == "PIPEDRIVE_CREATE_DEAL":
        if "value" in params and not params.get("currency"):
            return {"status": "error", "message": "Specify the deal currency before saving an amount."}
        endpoint, payload = "/v2/deals", params
    elif action == "MICROSOFTTEAMS_SEND_MESSAGE":
        endpoint = f"/v1.0/teams/{path_segment(params['team_id'])}/channels/{path_segment(params['channel_id'])}/messages"
        payload, result_key = {"body": {"contentType": "text", "content": params["message"]}}, "message_id"
    elif action == "TRELLO_CREATE_CARD":
        endpoint, payload, result_key = "/1/cards", params, "card_id"
    else:
        return {"status": "error", "message": "Integration action is not supported."}
    response = await client.post(f"{root}{endpoint}", headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    if data.get("errors") or data.get("success") is False:
        return {"status": "error", "message": "The external service did not confirm the action."}
    resource = data.get("data") if isinstance(data.get("data"), dict) else data
    if not resource.get("id"):
        return {"status": "unknown", "message": "The external service returned no record reference. Check the existing action before retrying."}
    return {"status": "success", result_key: resource["id"], "summary": "Action completed."}
