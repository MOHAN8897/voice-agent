"""The business writes its own emails and WhatsApp messages on the Integrations page.

No WhatsApp Business account is needed here: the provider is a mock that
records exactly what Dialtact would send through the Nango proxy.
"""
import base64
import email
import json
from email import policy
from types import SimpleNamespace

import httpx
import pytest

from server.services import nango_service as nango_module
from server.services.call_integrations import post_call_arguments
from server.services.integration_settings import (
    apply_email_format,
    clean_settings,
    filled_params,
    model_facing_schema,
    public_fields,
    render_message,
)
from server.services.nango_service import NangoService
from server.services.tool_schema_registry import _SCHEMAS, validate_tool_arguments

WHATSAPP = {"phone_number_id": "109876543210", "template_name": "call_follow_up", "template_language": "en"}
OUTCOME = {"summary_en": "Asked about whitening and booked a consultation for Saturday 11 AM.",
           "next_action": "Bring previous X-rays.", "extracted_fields": {"name": "Priya Sharma", "email": "priya@example.com"}}
INBOUND = {"direction": "inbound", "caller_id": "+91 98765 43210"}


def _tool(name: str) -> dict:
    return next(t for tools in _SCHEMAS.values() for t in tools if t["name"] == name)


def _mock_gateway(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(nango_module.httpx, "AsyncClient", lambda *a, **kw: real(transport=httpx.MockTransport(handler)))


# ------------------------------------------------------------------ settings
def test_message_fields_are_offered_with_caller_details_to_insert():
    gmail = {f["key"]: f for f in public_fields("GMAIL")}
    whatsapp = {f["key"]: f for f in public_fields("WHATSAPP")}
    assert {"writing_instructions", "follow_up_subject", "follow_up_body"} <= gmail.keys()
    assert {"writing_instructions", "follow_up_message"} <= whatsapp.keys()
    assert [p["key"] for p in gmail["follow_up_body"]["placeholders"]] == ["first_name", "name", "summary", "next_step"]
    assert whatsapp["follow_up_message"]["one_paragraph"] is True
    assert "placeholders" not in gmail["writing_instructions"]


def test_a_template_may_only_use_known_caller_details():
    saved = clean_settings("GMAIL", {"follow_up_subject": "Your visit, {first_name}",
                                     "follow_up_body": "Hi {first_name},\r\n\r\n{summary}\r\nNext: {next_step}"})
    assert saved["follow_up_body"] == "Hi {first_name},\n\n{summary}\nNext: {next_step}"
    with pytest.raises(ValueError, match=r"\{order_id\}"):
        clean_settings("GMAIL", {"follow_up_body": "Order {order_id} is ready"})
    with pytest.raises(ValueError, match="not a caller detail"):
        clean_settings("WHATSAPP", {**WHATSAPP, "follow_up_message": "Hi {customer}"})
    # Instructions are free text: braces there are not caller details.
    assert clean_settings("WHATSAPP", {**WHATSAPP, "writing_instructions": "Mention {our offer}"})["writing_instructions"]


def test_a_line_whose_detail_is_missing_is_left_out():
    template = "Hi {first_name},\n\n{summary}\n\nNext step: {next_step}\n\nThe Smile Studio"
    full = render_message(template, {"first_name": "Priya", "summary": "Booked Saturday.", "next_step": "Bring X-rays."})
    assert full == "Hi Priya,\n\nBooked Saturday.\n\nNext step: Bring X-rays.\n\nThe Smile Studio"
    partial = render_message(template, {"first_name": "", "summary": "Booked Saturday.", "next_step": ""})
    assert partial == "Hi there,\n\nBooked Saturday.\n\nThe Smile Studio"


# ------------------------------------------------------------------ after the call
def test_after_call_email_uses_the_business_template():
    settings = {"follow_up_subject": "Your visit to Smile Studio, {first_name}",
                "follow_up_body": "Dear {name},\n\nThanks for calling Smile Studio.\n\n{summary}\n\nBefore you come: {next_step}"}
    args = post_call_arguments("GMAIL_CREATE_DRAFT", OUTCOME, INBOUND, settings)
    assert args == {"to": "priya@example.com", "subject": "Your visit to Smile Studio, Priya",
                    "body": "Dear Priya Sharma,\n\nThanks for calling Smile Studio.\n\n"
                            "Asked about whitening and booked a consultation for Saturday 11 AM.\n\n"
                            "Before you come: Bring previous X-rays."}
    standard = post_call_arguments("GMAIL_CREATE_DRAFT", OUTCOME, INBOUND, {})
    assert standard["subject"] == "Following up on our call" and standard["body"].startswith("Hi Priya,")


def test_after_call_whatsapp_uses_the_business_message():
    settings = {**WHATSAPP, "follow_up_message": "Hi {first_name}, thanks for calling Smile Studio!\n{summary}\nNext: {next_step}"}
    args = post_call_arguments("WHATSAPP_SEND_MESSAGE", OUTCOME, INBOUND, settings)
    assert args["to"] == "+919876543210"
    assert args["message"].startswith("Hi Priya, thanks for calling Smile Studio!\nAsked about whitening")
    without_template = post_call_arguments("WHATSAPP_SEND_MESSAGE", OUTCOME, INBOUND, WHATSAPP)
    assert without_template["message"] == f"{OUTCOME['summary_en']} Next step: {OUTCOME['next_action']}"


# ------------------------------------------------------------------ during the call
def test_the_agent_is_given_the_business_writing_instructions():
    guide = "Thank them for calling Smile Studio and end with https://smile.example/book."
    email_tool = model_facing_schema(_tool("GMAIL_SEND_EMAIL"), {"writing_instructions": guide})
    assert email_tool["description"].endswith(f"Write it as the business asks: {guide}")
    whatsapp_tool = model_facing_schema(_tool("WHATSAPP_SEND_MESSAGE"), {**WHATSAPP, "writing_instructions": guide})
    assert guide in whatsapp_tool["description"]
    # Setup-owned values stay hidden from the model.
    assert set(whatsapp_tool["parameters"]["properties"]) == {"to", "message"}
    # No instructions: the schema is unchanged; other actions never carry them.
    assert model_facing_schema(_tool("GMAIL_SEND_EMAIL"), {}) == _tool("GMAIL_SEND_EMAIL")
    assert guide not in model_facing_schema(_tool("SLACK_SEND_MESSAGE"), {"writing_instructions": guide})["description"]


def test_details_the_business_wrote_may_be_sent(monkeypatch):
    from server.call import call_context
    from server.services import message_grounding, recipient_guard

    monkeypatch.setattr(call_context, "get", lambda call_id: SimpleNamespace(
        compiled_brain_text="Smile Studio, dental clinic.", business_answers=[], turn_action_results=[]))
    monkeypatch.setattr(recipient_guard, "caller_turns", lambda call_id: ["Please WhatsApp me the timings."])
    args = {"to": "+919876543210", "message": "We are open 10 AM to 8 PM. Call 080 4567 8910."}
    blocked = message_grounding.check("call-1", "WHATSAPP_SEND_MESSAGE", args)
    assert blocked and blocked["status"] == "error"
    allowed = message_grounding.check("call-1", "WHATSAPP_SEND_MESSAGE", args,
                                      business_text="Our hours are 10 AM to 8 PM; front desk 080 4567 8910.")
    assert allowed is None


# ------------------------------------------------------------------ the provider request
@pytest.mark.asyncio
async def test_whatsapp_follow_up_reaches_the_gateway_as_the_approved_template(monkeypatch):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.TEST123"}]})

    _mock_gateway(monkeypatch, handler)
    settings = {**WHATSAPP, "follow_up_message": "Hi {first_name}!\n\n{summary}\n\tNext: {next_step}"}
    # The same steps a finished call takes: build from the template, fill the
    # tenant's setup, validate, then send through the gateway.
    args = post_call_arguments("WHATSAPP_SEND_MESSAGE", OUTCOME, INBOUND, settings)
    args = {**args, **filled_params("WHATSAPP", "WHATSAPP_SEND_MESSAGE", settings)}
    assert validate_tool_arguments("WHATSAPP_SEND_MESSAGE", args) is None
    gateway = NangoService(secret_key="test-key", base_url="http://nango.test")
    result = await gateway._execute_proxy_tool("whatsapp-business", "conn-1", "WHATSAPP_SEND_MESSAGE", args)

    assert result["status"] == "sent" and result["message_id"] == "wamid.TEST123"
    assert "accepted by WhatsApp" in result["summary"]  # accepted, never claimed as delivered
    request = sent[0]
    assert str(request.url) == "http://nango.test/proxy/v25.0/109876543210/messages"
    assert request.headers["Connection-Id"] == "conn-1" and request.headers["Provider-Config-Key"] == "whatsapp-business"
    payload = json.loads(request.content)
    assert payload["to"] == "919876543210" and payload["type"] == "template"
    assert payload["template"]["name"] == "call_follow_up" and payload["template"]["language"] == {"code": "en"}
    text = payload["template"]["components"][0]["parameters"][0]["text"]
    # Meta rejects a template variable with line breaks, tabs or long runs of spaces.
    assert text == ("Hi Priya! Asked about whitening and booked a consultation for Saturday 11 AM. "
                    "Next: Bring previous X-rays.")


@pytest.mark.asyncio
async def test_a_rejected_whatsapp_message_is_reported_as_not_sent(monkeypatch):
    _mock_gateway(monkeypatch, lambda request: httpx.Response(400, json={"error": {"code": 132001, "message": "Template does not exist"}}))
    gateway = NangoService(secret_key="test-key", base_url="http://nango.test")
    result = await gateway._execute_proxy_tool("whatsapp-business", "conn-1", "WHATSAPP_SEND_MESSAGE",
                                               {"to": "+919876543210", "message": "Hi", **WHATSAPP})
    assert result["status"] == "error" and "HTTP 400" in result["message"]


@pytest.mark.asyncio
async def test_after_call_email_draft_carries_template_and_signature(monkeypatch):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"id": "r-draft-1"})

    _mock_gateway(monkeypatch, handler)
    settings = {"subject_prefix": "Smile Studio", "signature": "Smile Studio\n080 4567 8910",
                "follow_up_subject": "Your consultation, {first_name}", "follow_up_body": "Hi {first_name},\n\n{summary}"}
    args = post_call_arguments("GMAIL_CREATE_DRAFT", OUTCOME, INBOUND, settings)
    action, args, _ = apply_email_format("GMAIL_CREATE_DRAFT", args, settings)
    gateway = NangoService(secret_key="test-key", base_url="http://nango.test")
    result = await gateway._execute_proxy_tool("google-mail", "conn-2", action, args)

    assert result["status"] == "draft_created"
    assert str(sent[0].url) == "http://nango.test/proxy/gmail/v1/users/me/drafts"
    raw = json.loads(sent[0].content)["message"]["raw"]
    message = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=policy.default)
    assert message["To"] == "priya@example.com"
    assert message["Subject"] == "Smile Studio — Your consultation, Priya"
    assert message.get_content().strip() == (f"Hi Priya,\n\n{OUTCOME['summary_en']}\n\nSmile Studio\n080 4567 8910")
