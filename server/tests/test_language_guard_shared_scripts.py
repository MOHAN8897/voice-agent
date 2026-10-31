"""Languages that share a script keep their own letters in live text."""
from __future__ import annotations

import pytest

from server.realtime.language_guard import filter_unrelated_scripts


@pytest.mark.parametrize(
    "language, text",
    [
        ("hi-IN", "ग्राहक को 500 कार्ड चाहिए।"),
        ("mr-IN", "मला 500 कार्ड हवे."),
        ("te-IN", "నాకు 100 కార్డులు కావాలి."),
        ("ta-IN", "எனக்கு அட்டை வேண்டும்."),
        ("bn-IN", "আমার কার্ড চাই।"),
    ],
)
def test_configured_language_text_is_kept(language, text):
    assert filter_unrelated_scripts(text, language) == text


def test_foreign_script_is_still_removed_on_a_devanagari_call():
    assert filter_unrelated_scripts("मुझे 500 కార్డ్ चाहिए", "hi-IN") == "मुझे 500 चाहिए"
