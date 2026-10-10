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
        assert "/proxy/v2/users/me/meetings" in call_url
