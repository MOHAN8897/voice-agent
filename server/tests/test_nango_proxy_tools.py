"""Tests for Nango OAuth Proxy execution across catalog integrations."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from server.services.nango_service import nango_service

@pytest.mark.asyncio
async def test_proxy_slack_send_message():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"ok": True, "ts": "172828282.0001", "channel": "C12345"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="slack",
            connection_id="conn-123",
            action_name="SLACK_SEND_MESSAGE",
            params={"channel": "#general", "text": "Patient appointment scheduled"},
        )
        assert res["status"] == "success"
        assert res["message_id"] == "172828282.0001"
        assert "Slack channel #general" in res["summary"]
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/proxy/chat.postMessage" in call_url

@pytest.mark.asyncio
async def test_proxy_hubspot_create_contact():
    fake_resp = MagicMock()
    fake_resp.status_code = 201
    fake_resp.json.return_value = {"id": "hs-contact-999"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="hubspot",
            connection_id="conn-123",
            action_name="HUBSPOT_CREATE_CONTACT",
            params={"firstname": "Aarav", "lastname": "Patel", "email": "aarav@example.com", "phone": "+919876543210"},
        )
        assert res["status"] == "success"
        assert res["contact_id"] == "hs-contact-999"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/proxy/crm/v3/objects/contacts" in call_url

@pytest.mark.asyncio
async def test_proxy_github_create_issue():
    fake_resp = MagicMock()
    fake_resp.status_code = 201
    fake_resp.json.return_value = {"number": 42, "html_url": "https://github.com/acme/repo/issues/42"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="github-getting-started",
            connection_id="conn-123",
            action_name="GITHUB_CREATE_ISSUE",
            params={"owner": "acme", "repo": "repo", "title": "Lead bug report", "body": "Details"},
        )
        assert res["status"] == "success"
        assert res["issue_number"] == 42
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/proxy/repos/acme/repo/issues" in call_url

@pytest.mark.asyncio
async def test_proxy_notion_create_page():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"id": "page-1234", "url": "https://notion.so/page-1234"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="notion",
            connection_id="conn-123",
            action_name="NOTION_CREATE_PAGE",
            params={"parent_id": "db-123", "title": "Dental Call Note", "content": "Patient needs checkup"},
        )
        assert res["status"] == "success"
        assert res["page_id"] == "page-1234"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/proxy/v1/pages" in call_url

@pytest.mark.asyncio
async def test_proxy_zoom_create_meeting():
    fake_resp = MagicMock()
    fake_resp.status_code = 201
    fake_resp.json.return_value = {"join_url": "https://zoom.us/j/999888", "start_time": "2026-10-07T10:00:00Z", "topic": "Dental Video Consult"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="zoom",
            connection_id="conn-123",
            action_name="ZOOM_CREATE_MEETING",
            params={"topic": "Dental Video Consult", "start_time": "2026-10-07T10:00:00Z", "duration": 30},
        )
        assert res["status"] == "success"
        assert res["join_url"] == "https://zoom.us/j/999888"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        # Nango's zoom base_url already ends in /v2.
        assert call_url.endswith("/proxy/users/me/meetings")


@pytest.mark.asyncio
async def test_proxy_google_calendar_cancel_event():
    fake_resp = MagicMock()
    fake_resp.status_code = 204
    fake_resp.text = ""

    owned = MagicMock(status_code=200)
    owned.json.return_value = {"id": "event_abc_123", "attendees": [{"email": "caller@example.com"}]}
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=owned)), \
            patch("httpx.AsyncClient.delete", new_callable=AsyncMock, return_value=fake_resp) as mock_delete:
        res = await nango_service._execute_proxy_tool(
            provider_key="google-calendar",
            connection_id="conn-123",
            action_name="GOOGLECALENDAR_CANCEL_EVENT",
            params={"event_id": "event_abc_123", "attendee_email": "Caller@Example.com"},
        )
        assert res["status"] == "cancelled"
        assert res["event_id"] == "event_abc_123"
        assert "cancelled" in res["summary"]
        mock_delete.assert_called_once()
        call_url = mock_delete.call_args[0][0]
        assert "/proxy/calendar/v3/calendars/primary/events/event_abc_123" in call_url


@pytest.mark.asyncio
async def test_proxy_google_calendar_reschedule_event():
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {"id": "event_abc_123"}
    from server.services.integration_calendar import PARTY_KEY, party_tag

    owned = MagicMock(status_code=200)
    owned.json.return_value = {"id": "event_abc_123", "extendedProperties": {"private": {PARTY_KEY: party_tag("919800000000")}}}
    listing = MagicMock(status_code=200)
    listing.json.return_value = {"items": []}
    with patch("httpx.AsyncClient.get", AsyncMock(side_effect=[owned, listing])), patch("httpx.AsyncClient.patch", AsyncMock(return_value=fake_resp)) as mock_patch:
        result = await nango_service._execute_proxy_tool(provider_key="google-calendar", connection_id="conn-test",
            action_name="GOOGLECALENDAR_RESCHEDULE_EVENT", params={"event_id": "event_abc_123", "start": "2030-10-20T14:00:00+05:30", "end": "2030-10-20T14:30:00+05:30"},
            context={"party_phone": "919800000000"})
    assert result["status"] == "success" and result["confirmed"] and result["rescheduled"]
    assert result["event_id"] == "event_abc_123"
    mock_patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_free_slots_cover_the_whole_bookable_day():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Asia/Kolkata")
    metadata = MagicMock(status_code=200)
    metadata.json.return_value = {"timeZone": "Asia/Kolkata"}
    morning_busy = [(datetime(2030, 10, 20, 10, 0, tzinfo=zone), datetime(2030, 10, 20, 11, 0, tzinfo=zone))]
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=metadata)), \
            patch("server.services.integration_calendar._busy", AsyncMock(return_value=morning_busy)):
        result = await nango_service._execute_proxy_tool(provider_key="google-calendar", connection_id="conn-test",
            action_name="GOOGLECALENDAR_FIND_FREE_SLOTS", params={"date": "2030-10-20", "duration": 30})
    # Afternoon times are offered, not just the first few morning slots.
    assert "2030-10-20T16:30:00+05:30" in result["available_slots"]
    assert result["free_ranges"] == ["09:00-10:00", "11:00-17:00"]


@pytest.mark.asyncio
async def test_proxy_shopify_cancel_order():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.text = '{"order": {"id": 123456, "cancelled_at": "2026-10-14T14:00:00Z", "financial_status": "refunded"}}'
    fake_resp.json.return_value = {
        "order": {
            "id": 123456,
            "cancelled_at": "2026-10-14T14:00:00Z",
            "financial_status": "refunded",
        }
    }

    current = MagicMock(status_code=200)
    current.json.return_value = {"order": {"id": 123456, "fulfillment_status": None, "cancelled_at": None}}
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=current)), patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="shopify",
            connection_id="conn-123",
            action_name="SHOPIFY_CANCEL_ORDER",
            params={"order_id": "123456", "reason": "customer"},
        )
        assert res["status"] == "cancelled"
        assert res["order_id"] == "123456"
        assert "cancelled" in res["summary"]
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/proxy/admin/api/2026-07/orders/123456/cancel.json" in call_url


@pytest.mark.asyncio
async def test_proxy_calendly_cancel_event():
    fake_resp = MagicMock()
    fake_resp.status_code = 201
    fake_resp.text = '{"resource": {"canceled_at": "2026-10-14T14:00:00Z", "reason": "Caller rescheduled"}}'
    fake_resp.json.return_value = {
        "resource": {
            "canceled_at": "2026-10-14T14:00:00Z",
            "reason": "Caller rescheduled",
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_resp) as mock_post:
        res = await nango_service._execute_proxy_tool(
            provider_key="calendly",
            connection_id="conn-123",
            action_name="CALENDLY_CANCEL_EVENT",
            params={"event_uuid": "evt-uuid-999", "reason": "Caller rescheduled"},
        )
        assert res["status"] == "cancelled"
        assert res["event_uuid"] == "evt-uuid-999"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/proxy/scheduled_events/evt-uuid-999/cancellation" in call_url


@pytest.mark.asyncio
async def test_proxy_twilio_sms_get_status():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.text = '{"sid": "SM12345", "status": "delivered", "to": "+919876543210"}'
    fake_resp.json.return_value = {
        "sid": "SM12345",
        "status": "delivered",
        "to": "+919876543210",
    }

    accounts = MagicMock(status_code=200)
    accounts.json.return_value = {"accounts": [{"sid": "AC123", "status": "active"}]}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=[accounts, fake_resp]) as mock_get:
        res = await nango_service._execute_proxy_tool(
            provider_key="twilio",
            connection_id="conn-123",
            action_name="TWILIO_SMS_GET_STATUS",
            params={"message_sid": "SM12345"},
        )
        assert res["status"] == "success"
        assert res["delivery_status"] == "delivered"
        assert res["message_sid"] == "SM12345"
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0][0][0].endswith("/proxy/2010-04-01/Accounts.json")
        call_url = mock_get.call_args[0][0]
        assert call_url.endswith("/proxy/2010-04-01/Accounts/AC123/Messages/SM12345.json")




@pytest.mark.asyncio
async def test_calendar_never_changes_or_reads_another_callers_appointment():
    """A caller may only see, cancel or move appointments booked by them."""
    other = MagicMock(status_code=200)
    other.json.return_value = {"id": "evt-other", "summary": "Dr visit - Priya", "attendees": [{"email": "priya@example.com"}]}
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=other)), \
            patch("httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_delete:
        res = await nango_service._execute_proxy_tool(provider_key="google-calendar", connection_id="conn",
            action_name="GOOGLECALENDAR_CANCEL_EVENT", params={"event_id": "evt-other", "attendee_email": "me@example.com"},
            context={"party_phone": "919811111111"})
    assert res["status"] == "error"
    mock_delete.assert_not_awaited()

    meta = MagicMock(status_code=200)
    meta.json.return_value = {"timeZone": "Asia/Kolkata"}
    events = MagicMock(status_code=200)
    events.json.return_value = {"items": [
        {"id": "evt-other", "summary": "Dr visit - Priya", "attendees": [{"email": "priya@example.com"}]},
        {"id": "evt-mine", "summary": "Cleaning", "attendees": [{"email": "me@example.com"}]},
    ]}
    with patch("httpx.AsyncClient.get", AsyncMock(side_effect=[meta, events])):
        res = await nango_service._execute_proxy_tool(provider_key="google-calendar", connection_id="conn",
            action_name="GOOGLECALENDAR_LIST_EVENTS", params={"date": "2030-01-02", "attendee_email": "me@example.com"})
    assert [e["id"] for e in res["events"]] == ["evt-mine"]
