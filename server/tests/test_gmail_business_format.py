"""The business, not the model, decides how its emails look and whether a person reviews them."""
from __future__ import annotations

import pytest

from server.services.integration_settings import apply_email_format, clean_settings, is_configured


def test_gmail_works_without_any_setup():
    assert is_configured("GMAIL", {})
    name, args, held = apply_email_format("GMAIL_SEND_EMAIL", {"to": "a@b.co", "subject": "Prices", "body": "Hi"}, None)
    assert (name, held) == ("GMAIL_SEND_EMAIL", False)
    assert args == {"to": "a@b.co", "subject": "Prices", "body": "Hi"}


def test_subject_prefix_and_signature_are_added_once():
    saved = {"subject_prefix": "Mohan Constructions", "signature": "Regards,\nMohan Constructions\n+91 90000 00000"}
    _, args, _ = apply_email_format("GMAIL_SEND_EMAIL", {"to": "a@b.co", "subject": "Site visit", "body": "Your visit is at 3 PM."}, saved)
    assert args["subject"] == "Mohan Constructions — Site visit"
    assert args["body"].endswith("Regards,\nMohan Constructions\n+91 90000 00000")
    _, again, _ = apply_email_format("GMAIL_SEND_EMAIL", args, saved)
    assert again == args  # applying twice changes nothing


def test_review_mode_turns_a_send_into_a_draft():
    name, _, held = apply_email_format("GMAIL_SEND_EMAIL", {"to": "a@b.co", "subject": "s", "body": "b"}, {"send_mode": "draft"})
    assert (name, held) == ("GMAIL_CREATE_DRAFT", True)


def test_settings_accept_a_multiline_signature_and_only_known_choices():
    out = clean_settings("GMAIL", {"send_mode": "draft", "signature": "Regards,\r\nMohan\r\n"})
    assert out == {"send_mode": "draft", "signature": "Regards,\nMohan"}
    with pytest.raises(ValueError):
        clean_settings("GMAIL", {"send_mode": "blast"})
    with pytest.raises(ValueError):
        clean_settings("GMAIL", {"subject_prefix": "line one\nline two"})  # single-line field


def test_open_links_point_at_the_workspaces_own_sheet_drafts_and_calendar():
    from server.services.integration_settings import open_link

    sheet = open_link("GOOGLESHEETS", {"spreadsheet_id": "https://docs.google.com/spreadsheets/d/19EIbpMC5WaENfcJYtPTJTSNrnVM8EOzHYOQq8hHeLjg/edit#gid=0"})
    assert sheet == {"url": "https://docs.google.com/spreadsheets/d/19EIbpMC5WaENfcJYtPTJTSNrnVM8EOzHYOQq8hHeLjg/edit", "label": "Open sheet"}
    assert open_link("GOOGLESHEETS", {}) is None  # no sheet chosen yet: no link
    assert open_link("GMAIL", {"send_mode": "draft"})["url"].endswith("#drafts")
    assert open_link("GMAIL", {})["url"].endswith("#sent")
    assert open_link("SLACK", {"channel": "C1"}) is None
