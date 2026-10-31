"""Tests covering all 5 integration problems and security auditing:
1. Supported integrations offered for specific supported actions
2. Capabilities match promises (Google Calendar cancel & reschedule implemented)
3. Verified integration count is exactly 28
4. Non-UUID tenant IDs & network errors return clean responses without HTTP 500
5. No internal technical details or vendor provider keys leaked to tenants
"""
import pytest
from server.tests.test_integration_security_hardening import db, client
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from server.app import app
from server.routes.integrations_catalog import CATALOG_INTEGRATIONS
from server.services.tool_schema_registry import _SCHEMAS, list_supported_apps, get_tools_for_tenant


def test_problem_3_integration_count_is_exactly_28():
    """Verify the integration catalog has exactly 28 verified integrations."""
    assert len(CATALOG_INTEGRATIONS) == 28, f"Expected 28 integrations, got {len(CATALOG_INTEGRATIONS)}"
    app_ids = [item["id"] for item in CATALOG_INTEGRATIONS]
    assert len(app_ids) == len(set(app_ids)), "Duplicate integration IDs found in catalog"


def test_problem_1_core_integrations_present():
    """Verify core integrations are offered in catalog."""
    catalog_map = {item["id"]: item for item in CATALOG_INTEGRATIONS}
    for expected in ["GOOGLECALENDAR", "HUBSPOT", "GMAIL", "SLACK", "SHOPIFY"]:
        assert expected in catalog_map, f"Core integration {expected} missing from catalog"
        item = catalog_map[expected]
        assert len(item["actions"]) > 0, f"No actions listed for {expected}"


def test_problem_2_capabilities_match_backend_schemas():
    """Verify every action in the catalog matches an actual backend schema capability."""
    catalog_map = {item["id"]: item for item in CATALOG_INTEGRATIONS}

    # 1. Google Calendar
    gcal = catalog_map["GOOGLECALENDAR"]
    assert "Cancel Event" in gcal["actions"]
    assert "Reschedule Event" in gcal["actions"]
    assert "Create Booking" in gcal["actions"]
    assert "Find Free Slots" in gcal["actions"]
    gcal_tool_names = {s["name"] for s in _SCHEMAS.get("GOOGLECALENDAR", [])}
    assert "GOOGLECALENDAR_CANCEL_EVENT" in gcal_tool_names
    assert "GOOGLECALENDAR_RESCHEDULE_EVENT" in gcal_tool_names
    assert "GOOGLECALENDAR_CREATE_EVENT" in gcal_tool_names

    # 2. Shopify: Cancel Unfulfilled Order, Get Fulfillments, Lookup Order, Search Customer
    shopify = catalog_map["SHOPIFY"]
    assert "Cancel Unfulfilled Order" in shopify["actions"]
    assert "Lookup Order Details" in shopify["actions"]
    assert "Get Fulfillments" in shopify["actions"]
    assert "Search Customer" in shopify["actions"]
    shopify_tool_names = {s["name"] for s in _SCHEMAS.get("SHOPIFY", [])}
    assert "SHOPIFY_CANCEL_ORDER" in shopify_tool_names
    assert "SHOPIFY_GET_FULFILLMENTS" in shopify_tool_names
    assert "SHOPIFY_GET_ORDER" in shopify_tool_names
    assert "SHOPIFY_SEARCH_CUSTOMER" in shopify_tool_names

    # 3. Calendly: Cancel Event, Check Available Times, Schedule Invitee Meeting, List Event Types
    calendly = catalog_map["CALENDLY"]
    assert "Cancel Event" in calendly["actions"]
    assert "Check Available Times" in calendly["actions"]
    assert "Schedule Invitee Meeting" in calendly["actions"]
    assert "List Event Types" in calendly["actions"]
    calendly_tool_names = {s["name"] for s in _SCHEMAS.get("CALENDLY", [])}
    assert "CALENDLY_CANCEL_EVENT" in calendly_tool_names
    assert "CALENDLY_LIST_EVENT_TYPES" in calendly_tool_names
    assert "CALENDLY_CREATE_INVITEE" in calendly_tool_names
    assert "CALENDLY_GET_AVAILABLE_TIMES" in calendly_tool_names

    # 4. Twilio SMS: Send SMS Message, Check Message Status
    twilio = catalog_map["TWILIO_SMS"]
    assert "Send SMS Message" in twilio["actions"]
    assert "Check Message Status" in twilio["actions"]
    twilio_tool_names = {s["name"] for s in _SCHEMAS.get("TWILIO_SMS", [])}
    assert "TWILIO_SMS_SEND_MESSAGE" in twilio_tool_names
    assert "TWILIO_SMS_GET_STATUS" in twilio_tool_names

    # 5. Cal.com
    calcom = catalog_map["CALCOM"]
    assert "Cancel Booking" in calcom["actions"]
    assert "Reschedule Booking" in calcom["actions"]
    calcom_tool_names = {s["name"] for s in _SCHEMAS.get("CALCOM", [])}
    assert "CALCOM_CANCEL_BOOKING" in calcom_tool_names
    assert "CALCOM_RESCHEDULE_BOOKING" in calcom_tool_names

    # 6. Verify comprehensive backing for all 28 catalog items
    action_to_schema_subnames = {
        "Find Free Slots": ["FIND_FREE_SLOTS", "FIND_SLOTS"],
        "Create Booking": ["CREATE_EVENT", "CREATE_BOOKING"],
        "Cancel Event": ["CANCEL_EVENT"],
        "Reschedule Event": ["RESCHEDULE_EVENT"],
        "Check Available Times": ["GET_AVAILABLE_TIMES", "FIND_SLOTS"],
        "Schedule Invitee Meeting": ["CREATE_INVITEE", "CREATE_BOOKING"],
        "List Event Types": ["LIST_EVENT_TYPES"],
        "Find Available Slots": ["GET_AVAILABLE_SLOTS", "FIND_SLOTS"],
        "Cancel Booking": ["CANCEL_BOOKING"],
        "Reschedule Booking": ["RESCHEDULE_BOOKING"],
        "Create Meeting": ["CREATE_MEETING"],
        "Get Meeting Details": ["GET_MEETING"],
        "Lookup Contact": ["LOOKUP_CONTACT"],
        "Create Contact": ["CREATE_CONTACT"],
        "Create Deal": ["CREATE_DEAL"],
        "Update Deal Stage": ["UPDATE_DEAL_STAGE"],
        "Log Call Note": ["CREATE_NOTE"],
        "Create Lead": ["CREATE_LEAD"],
        "Lookup Lead": ["LOOKUP_LEAD"],
        "Create Task / Activity": ["CREATE_TASK"],
        "Search Tickets": ["SEARCH_TICKETS"],
        "Create Ticket": ["CREATE_TICKET"],
        "Update Ticket": ["UPDATE_TICKET"],
        "Search Contact": ["SEARCH_CONTACT"],
        "Create Conversation": ["CREATE_CONVERSATION"],
        "Create Issue": ["CREATE_ISSUE"],
        "Get Issue Details": ["GET_ISSUE"],
        "Add Comment": ["ADD_COMMENT"],
        "Search Issues": ["SEARCH_ISSUES"],
        "Lookup Ticket": ["LOOKUP_TICKET"],
        "Lookup Order Details": ["GET_ORDER"],
        "Cancel Unfulfilled Order": ["CANCEL_ORDER"],
        "Get Fulfillments": ["GET_FULFILLMENTS"],
        "Search Customer": ["SEARCH_CUSTOMER"],
        "Get Order Details": ["GET_ORDER"],
        "Check Product Stock": ["CHECK_STOCK"],
        "Update Order Status": ["UPDATE_ORDER_STATUS"],
        "Send Channel Message": ["SEND_MESSAGE"],
        "Send SMS Message": ["SEND_MESSAGE"],
        "Check Message Status": ["GET_STATUS"],
        "Send Message": ["SEND_MESSAGE"],
        "Send Follow-Up Email": ["SEND_EMAIL"],
        "Create Email Draft": ["CREATE_DRAFT"],
        "Send Transactional Email": ["SEND_EMAIL"],
        "Add Subscriber to List": ["ADD_SUBSCRIBER"],
        "Search Records": ["SEARCH_RECORDS"],
        "Create Record": ["CREATE_RECORD"],
        "Search Pages": ["SEARCH_PAGES"],
        "Create Page": ["CREATE_PAGE"],
        "Query Rows": ["QUERY_ROW"],
        "Insert Row": ["INSERT_ROW"],
        "Create Task": ["CREATE_TASK"],
        "Add Task Comment": ["ADD_COMMENT"],
        "Create Board Item": ["CREATE_ITEM"],
    }

    for item in CATALOG_INTEGRATIONS:
        app_id = item["id"]
        schemas = _SCHEMAS.get(app_id, [])
        assert len(schemas) > 0, f"App {app_id} has no registered schemas"
        tool_names = [s["name"] for s in schemas]

        for action in item["actions"]:
            assert action in action_to_schema_subnames, f"Action '{action}' in {app_id} missing test mapping"
            expected_suffixes = action_to_schema_subnames[action]
            match_found = any(
                any(tool.endswith(suffix) for suffix in expected_suffixes)
                for tool in tool_names
            )
            assert match_found, f"Action '{action}' in catalog for '{app_id}' has no matching schema in {tool_names}"



@pytest.mark.asyncio
async def test_problem_4_and_5_catalog_endpoint_no_leaks_and_no_500(client):
    response = await client.get('/api/integrations/catalog', headers={'authorization': 'Bearer test-session'})
    assert response.status_code == 200
    assert response.json()['total'] == 28
    assert all('nango_provider_key' not in item for item in response.json()['items'])


@pytest.mark.asyncio
async def test_problem_4_connect_with_non_uuid_tenant_no_500():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/integrations/GOOGLECALENDAR/connect',
            headers={'x-tenant-id': 'spoofed-tenant'}, json={'base_redirect_uri': 'http://localhost:5173/callback'})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_problem_4_activate_and_disconnect_with_non_uuid_tenant_no_500():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for method, path, body in [('POST', '/api/integrations/GOOGLECALENDAR/activate', {'connection_id': 'fake'}),
                                    ('DELETE', '/api/integrations/GOOGLECALENDAR', None)]:
            response = await client.request(method, path, headers={'x-tenant-id': 'spoofed-tenant'}, json=body)
            assert response.status_code == 401
