"""Semantic validation tests — Phase 2."""
from server.brain.semantic_validation import validate_sections


def test_blocking_empty_required_section():
    sections = [
        {"section_id": "1", "type": "identity_purpose", "raw_text": "", "enabled": True},
        {"section_id": "2", "type": "facts", "raw_text": "ok", "enabled": True},
        {"section_id": "3", "type": "guardrails", "raw_text": "never invent", "enabled": True},
    ]
    result = validate_sections(sections)
    assert result.ok is False
    assert any(i.code == "required_empty" for i in result.issues)


def test_warning_and_blocking_severity():
    sections = [
        {"section_id": "1", "type": "identity_purpose", "raw_text": "hi", "enabled": True},
        {"section_id": "2", "type": "facts", "raw_text": "refund within 7 days", "enabled": True},
        {"section_id": "3", "type": "guardrails", "raw_text": "refund within 14 days", "enabled": True},
    ]
    result = validate_sections(sections)
    assert result.ok is False
    assert any(i.severity == "blocking" for i in result.issues)
