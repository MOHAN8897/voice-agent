"""Verification test suite validating language pack audit findings against industry standards.

Ensures:
1. Native-script conversational opening templates across Indic locales (no Romanized speech).
2. Gender-neutral openings avoiding hardcoded persona assumptions.
3. Natural polite repairs (Tamil colloquial, Telugu filler agreement, etc.).
4. Optional acknowledgment guidance (no forced acknowledgment prefixes).
5. Respectful Marathi (तुम्ही) and contextual Bengali vocabulary.
6. Valid short replies cover native acknowledgments across all languages.
7. Legacy script-writer length guardrail aligns with the 1-2 sentence conversational contract.
"""
from __future__ import annotations

import re
import pytest

from server.config.constants import Constants
from server.prompts.agent_voice_rules import (
    OPENING_NAME_ONLY,
    OPENING_NO_COMPANY,
    OPENING_OUTBOUND_NAME_ONLY,
    OPENING_OUTBOUND_NO_COMPANY,
    OPENING_OUTBOUND_WITH_COMPANY,
    OPENING_OUTBOUND_WITH_COMPANY_PURPOSE,
    OPENING_WITH_COMPANY,
    OPENING_WITH_COMPANY_PURPOSE,
    PHONE_ASK_FALLBACK,
    SLOW_DOWN_FALLBACK,
    SPOKEN_PACKS,
    UNCLEAR_FALLBACK,
)
from server.prompts.indic_spoken_packs import INDIC_SPOKEN_PACKS
from server.prompts.spoken_locale_style import SPOKEN_LOCALES

INDIC_LOCALES = ("te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN")
ALL_LOCALES = tuple(Constants.SUPPORTED_LANGUAGES)

ALL_OPENING_DICTS = [
    OPENING_WITH_COMPANY,
    OPENING_OUTBOUND_WITH_COMPANY,
    OPENING_WITH_COMPANY_PURPOSE,
    OPENING_OUTBOUND_WITH_COMPANY_PURPOSE,
    OPENING_NO_COMPANY,
    OPENING_OUTBOUND_NO_COMPANY,
    OPENING_NAME_ONLY,
    OPENING_OUTBOUND_NAME_ONLY,
]


def test_all_locales_present_in_openings() -> None:
    for opening_dict in ALL_OPENING_DICTS:
        for locale in ALL_LOCALES:
            assert locale in opening_dict, f"Missing locale {locale} in opening dict"
            assert opening_dict[locale].strip(), f"Empty template for {locale}"


def test_no_romanized_indic_openings() -> None:
    roman_indicators = [
        "nenu", "meeru", "sahayam kavali", "bol rahi", "bolto aahe",
        "pesuren", "pesalaama", "matladabahuda", "samsarikkamo", "madat kar",
        "sahajjo korte", "madad karva", "gall kar sakde", "kotha bolte",
    ]
    for opening_dict in ALL_OPENING_DICTS:
        for locale in INDIC_LOCALES:
            template = opening_dict[locale].lower()
            # Remove allowed template variables like {name}, {company}, {work}, {purpose}, moment
            cleaned = re.sub(r"\{(?:name|company|work|purpose)\}", "", template)
            cleaned = cleaned.replace("moment", "")
            for roman in roman_indicators:
                assert roman not in cleaned, (
                    f"Found Romanized text '{roman}' in {locale} opening template: '{opening_dict[locale]}'"
                )


def test_no_hardcoded_gender_in_openings() -> None:
    gendered_phrases = [
        "bol rahi hoon", "bol raha hoon",
        "kar sakdi haan", "kar sakda haan",
        "bolto aahe", "shakto",
    ]
    for opening_dict in ALL_OPENING_DICTS:
        for locale in ALL_LOCALES:
            template = opening_dict[locale]
            for gendered in gendered_phrases:
                assert gendered not in template, (
                    f"Found gendered phrase '{gendered}' in {locale} template: '{template}'"
                )


def test_telugu_repairs_avoid_standalone_andi() -> None:
    # Standalone 'అండి' should not be used in fixed repair lines
    te_unclear = UNCLEAR_FALLBACK["te-IN"]
    te_slow = SLOW_DOWN_FALLBACK["te-IN"]
    assert " అండి" not in te_unclear and not te_unclear.startswith("అండి")
    assert " అండి" not in te_slow and not te_slow.startswith("అండి")


def test_tamil_repairs_use_natural_spoken_forms() -> None:
    ta_unclear = UNCLEAR_FALLBACK["ta-IN"]
    ta_slow = SLOW_DOWN_FALLBACK["ta-IN"]
    # Should use conversational 'கேட்கல' rather than bookish 'தெளிவாகக் கேட்கவில்லை'
    assert "தெளிவாகக் கேட்கவில்லை" not in ta_unclear
    assert "கேட்கல" in ta_unclear
    # Should use conversational 'மெதுவா' rather than bookish 'மெதுவாக'
    assert "மெதுவா" in ta_slow


def test_marathi_uses_respectful_tumhi() -> None:
    mr_style = SPOKEN_LOCALES["mr-IN"]
    assert "तुम्ही" in mr_style.register
    assert "aapan" not in mr_style.register.lower()
    mr_pack = INDIC_SPOKEN_PACKS["mr-IN"]
    assert "तुम्ही" in mr_pack


def test_bengali_style_does_not_blacklist_proyojoniyo() -> None:
    bn_style = SPOKEN_LOCALES["bn-IN"]
    assert "প্রয়োজনীয়" not in bn_style.register


def test_filler_bans_emphasize_optional_acknowledgments() -> None:
    # Verify indicative spoken packs emphasize acknowledgments as optional or when useful
    for loc in ("ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"):
        pack = INDIC_SPOKEN_PACKS[loc]
        assert any(phrase in pack for phrase in ["acknowledge when useful", "acknowledge when helpful", "optional"]), (
            f"Expected acknowledgment guidance in {loc} pack"
        )


def test_all_locales_filler_bans_are_optional_not_forced_rotation() -> None:
    for locale in ALL_LOCALES:
        pack = SPOKEN_PACKS[locale]
        assert "vary naturally with" not in pack, f"Pack {locale} still tells model to 'vary naturally with' rotation"


def test_indic_spoken_packs_have_rich_voice_examples() -> None:
    assert "ആലോചിക്കട്ടെ" in INDIC_SPOKEN_PACKS["ml-IN"]
    assert "विचार करतो" in INDIC_SPOKEN_PACKS["mr-IN"]
    assert "একটু ভাবছি" in INDIC_SPOKEN_PACKS["bn-IN"]
    assert "વિચારું છું" in INDIC_SPOKEN_PACKS["gu-IN"]
    assert "ਸੋਚਦਾ ਹਾਂ" in INDIC_SPOKEN_PACKS["pa-IN"]


def test_slow_down_repairs_are_natural_and_polite() -> None:
    assert SLOW_DOWN_FALLBACK["hi-IN"] == "कृपया थोड़ा धीरे बोलेंगे?"
    assert SLOW_DOWN_FALLBACK["mr-IN"] == "कृपया थोडं हळू बोलाल का?"


def test_valid_short_replies_cover_all_supported_locales() -> None:
    from server.services.voice_pipeline_limits import is_incomplete_spoken_crumb, _VALID_SHORT_REPLY

    native_acks = [
        "ok", "okay", "yes", "sure", "thanks", "got it", "noted",
        "సరే", "అవును", "అలాగే",
        "हाँ", "ठीक", "ठीक है", "जी",
        "சரி", "ஆமாம்", "சரிங்க",
        "ಸರಿ", "ಹೌದು", "ಖಂಡಿತ",
        "ശരി", "അതെ", "തീർച്ചയായും",
        "हो", "ठीक आहे", "नक्कीच",
        "হ্যাঁ", "ঠিক আছে", "নিশ্চয়ই",
        "હા", "બરાબર", "સારું",
        "ਹਾਂਜੀ", "ਠੀਕ ਹੈ",
    ]
    for ack in native_acks:
        assert _VALID_SHORT_REPLY.match(ack), f"'{ack}' not matched by _VALID_SHORT_REPLY"
        assert not is_incomplete_spoken_crumb(ack), f"'{ack}' flagged as incomplete crumb"


def test_personal_openings_across_all_locales_are_native_script() -> None:
    from server.brain.agent_script_compiler import _personal_opening_line

    for locale in INDIC_LOCALES:
        inbound = _personal_opening_line(
            agent_name="Priya", callee_name="Rahul", language=locale, direction="inbound", is_test=True
        )
        outbound = _personal_opening_line(
            agent_name="Priya", callee_name="Rahul", language=locale, direction="outbound", is_test=False
        )
        assert "Rahul" in inbound
        assert "Rahul" in outbound
        assert "bol rahi" not in inbound and "bol rahi" not in outbound
        assert "nenu Priya." not in inbound
        assert "Nenu ela sahayam" not in inbound


def test_legacy_script_writer_length_guardrail_aligned() -> None:
    from server.prompts.agent_voice_rules import script_writer_system

    for locale in ALL_LOCALES:
        prompt = script_writer_system(language=locale, budget_tokens=2000)
        assert "simple 15–55" not in prompt
        assert "Platform speech length target is 1–2 conversational sentences" in prompt

def test_indic_combining_characters_detected_across_all_scripts() -> None:
    from server.services.voice_pipeline_limits import _is_indic_combining

    # Test combining marks (virama / vowel signs) across all 9 Indic scripts
    indic_marks = [
        ("్", "Telugu virama"),
        ("ా", "Telugu aa"),
        ("्", "Devanagari virama"),
        ("ा", "Devanagari aa"),
        ("்", "Tamil virama"),
        ("ா", "Tamil aa"),
        ("್", "Kannada virama"),
        ("ಾ", "Kannada aa"),
        ("്", "Malayalam virama"),
        ("ാ", "Malayalam aa"),
        ("্", "Bengali virama"),
        ("া", "Bengali aa"),
        ("્", "Gujarati virama"),
        ("ા", "Gujarati aa"),
        ("੍", "Gurmukhi virama"),
        ("ਾ", "Gurmukhi aa"),
    ]
    for ch, name in indic_marks:
        assert _is_indic_combining(ch), f"Failed to identify {name} as combining mark"

    # Base consonants and Latin characters must not be identified as combining marks
    for base in ["క", "क", "க", "ಕ", "ക", "ক", "ક", "ਕ", "a", "Z", "1", " "]:
        assert not _is_indic_combining(base), f"Base char {base} incorrectly marked combining"

