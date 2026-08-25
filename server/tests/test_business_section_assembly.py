"""Deterministic business section assembly — Phase 2."""
from server.brain.business_brain_store import assemble_raw_business_prompt


def test_assembly_preserves_raw_text_byte_for_byte():
    sections = [
        {
            "section_id": "a",
            "type": "facts",
            "title": "Business Facts",
            "raw_text": "Refund window is 7 days.",
            "order": 20,
            "enabled": True,
        },
        {
            "section_id": "b",
            "type": "identity_purpose",
            "title": "Identity",
            "raw_text": "You are a Telugu assistant.",
            "order": 10,
            "enabled": True,
        },
    ]
    raw, checksum = assemble_raw_business_prompt(sections)
    assert "<!-- section:identity_purpose:b -->" in raw
    assert "You are a Telugu assistant." in raw
    assert "Refund window is 7 days." in raw
    assert checksum
    assert raw.index("identity_purpose") < raw.index("facts")


def test_disabled_sections_excluded():
    sections = [
        {"section_id": "a", "type": "faq", "raw_text": "hidden", "order": 10, "enabled": False},
        {"section_id": "b", "type": "facts", "raw_text": "visible", "order": 20, "enabled": True},
    ]
    raw, _ = assemble_raw_business_prompt(sections)
    assert "hidden" not in raw
    assert "visible" in raw
