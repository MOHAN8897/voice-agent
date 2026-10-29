"""Recipient data must mean the same thing at import, generation and call startup."""
import pytest
from fastapi import HTTPException

from server.services.saas.contact_import_service import (
    detect_column_mappings, normalize_and_validate_contacts,
    render_agent_prompt_for_contact, validate_agent_variables_against_contacts,
)
from server.services.saas.script_variables import merge_variables, variables_from_text
from server.services.saas.campaign_script import require_campaign_variables


def test_real_csv_mapping_contract_reaches_call_script_without_guessing():
    rows = [{"Mobile No": "+12025550101", "Customer Name": "A. Sai Kumar", "Appointment Date": "2026-11-02"}]
    detected = detect_column_mappings(list(rows[0]), rows)
    mapping = {key: value["field"] for key, value in detected.items()}
    normalized = normalize_and_validate_contacts(rows, mapping, "US")
    contact = normalized["valid_contacts"][0]
    script = "Hello {{contact.full_name}}, your appointment is {{contact.custom_fields.appointment_date}}."
    report = require_campaign_variables(script, [contact])
    assert report["valid"]
    assert report["previews"][0]["renderedText"] == "Hello A. Sai Kumar, your appointment is 2026-11-02."
    assert render_agent_prompt_for_contact("{{name}} / {{customer_name}} / {{full_name}}", contact) == "A. Sai Kumar / A. Sai Kumar / A. Sai Kumar"


def test_fallback_satisfies_optional_occurrence_but_not_a_second_required_use():
    contact = {"phone": "+12025550101"}
    assert validate_agent_variables_against_contacts(["Hello {{contact.full_name | there}}"], [contact])["valid"]
    report = validate_agent_variables_against_contacts(["{{contact.full_name | there}} then {{contact.full_name}}"], [contact])
    assert report["missing_breakdown"] == {"contact.full_name": 1}
    assert report["missing_contact_indices"] == [0]
    with pytest.raises(HTTPException) as failure:
        require_campaign_variables("Hello {{contact.full_name}}", [contact])
    assert failure.value.status_code == 422


def test_metadata_understands_editor_syntax_and_does_not_invent_variables():
    text = "{{contact.full_name | there}} {{contact.custom_fields.product || service}}"
    assert [item["key"] for item in variables_from_text("", text)] == ["contact.full_name", "contact.custom_fields.product"]
    assert variables_from_text("Hello", "Ask how you can help") == []
    assert merge_variables([{"key": "unused"}], "", text) == variables_from_text("", text)


def test_old_generated_variable_legends_are_not_required_recipient_fields():
    text = "Hello.\n--- RUNTIME TAGS (fill when known) ---\n{{caller_name}}: Name\n{{callback_phone}}: Phone\n--- SAFETY ---\nBe professional."
    assert require_campaign_variables(text, [{"phone": "+12025550101"}])["variables_used"] == []
    rendered = render_agent_prompt_for_contact(text, {})
    assert "RUNTIME TAGS" not in rendered and "Be professional." in rendered


def test_duplicate_destination_columns_are_rejected_instead_of_overwriting_names():
    with pytest.raises(ValueError, match="only one column"):
        normalize_and_validate_contacts([], {"Name": "full_name", "Customer": "full_name"})


@pytest.mark.parametrize("tag", ["{{contact.first-name}}", "{{first name}}", "{{contact.full_name", "{{}}"])
def test_malformed_placeholders_block_campaigns_before_dialing(tag):
    report = validate_agent_variables_against_contacts([f"Hello {tag}"], [{"full_name": "Example Contact"}])
    assert not report["valid"] and report["invalid_placeholders"]
    with pytest.raises(HTTPException) as error:
        require_campaign_variables(f"Hello {tag}", [{"full_name": "Example Contact"}])
    assert error.value.detail["error"]["code"] == "script_variables_invalid"


@pytest.mark.asyncio
async def test_generated_script_personalizes_the_primary_gemini_prompt():
    from server.brain.agent_script_compiler import compile_agent_from_brief
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
    compiled, _, *_ = await compile_agent_from_brief(
        brief="We are Example Clinic. Agent Maya. Outbound appointment reminders. Address the customer as {{contact.full_name | there}}. Remind them of {{contact.custom_fields.appointment_date}}.",
        language="en-IN", use_llm=False, interpret_brief=False,
    )
    contact = {"full_name": "Example Contact", "phone": "+12025550101", "custom_fields": {"appointment_date": "November 2"}}
    assert require_campaign_variables(compiled, [contact])["valid"]
    rendered = render_agent_prompt_for_contact(compiled, contact)
    instructions = build_gemini_audio_session_instructions(rendered, language="en-IN", direction="outbound")
    assert "Example Contact" in instructions and "November 2" in instructions
    assert "{{contact." not in instructions


@pytest.mark.parametrize("token", ["{{contact.unknown}}", "{{contact.full_name", "{{}}"])
def test_generation_rejects_invented_or_malformed_runtime_variables(token):
    from server.brain.agent_script_compiler import validate_agent_script
    reasons = validate_agent_script(f"You are Maya from Example Clinic. Hello {token}.",
                                    brief="Maya from Example Clinic handles appointment reminders.", agent_name="Maya")
    assert "placeholder tokens remain in script" in reasons
