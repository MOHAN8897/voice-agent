"""The simulator's deterministic speech checks must catch real TTS hazards and accept natural code-mixing."""
from server.eval.conversation_sim.checks import check_reply


def test_natural_code_mixed_indic_reply_passes():
    for text, lang in [("Split AC servicing కి ₹599 అవుతుంది.", "te-IN"),
                       ("Window AC का charge ₹499 है।", "hi-IN"),
                       ("Split AC servicing નો ચાર્જ ₹599 છે.", "gu-IN"),
                       ("Split AC servicing-ന് ₹599 ആകും.", "ml-IN")]:
        result = check_reply(text, language=lang, tts_provider="sarvam", tts_model="bulbul:v3")
        assert result.passed, (lang, result)


def test_tts_hazards_are_hard_failures():
    hazards = {
        "**Price** is ₹599.": "markdown",
        "Price is ₹599": "no_terminal_punctuation",
        "<laugh> Sure, ₹599.": "audio_tag_for_plain_tts:laugh",
        "Split AC servicing costs 599 rupees.": "no_native_script",
        "స్ప్లిట్ ఏసీ ధర ₹599 है।": "wrong_indic_script",
    }
    for text, code in hazards.items():
        language = "en-IN" if code in {"markdown", "no_terminal_punctuation", "audio_tag_for_plain_tts:laugh"} else "te-IN"
        assert code in check_reply(text, language=language, tts_provider="sarvam", tts_model="bulbul:v3").hard


def test_gnani_v3_tags_allowed_only_from_catalog_and_not_trailing():
    ok = check_reply("సరే. <excited> మీ booking confirm అయింది.", language="te-IN", tts_provider="gnani", tts_model="timbre-v3.0")
    assert ok.passed
    bad = check_reply("సరే <dance> అవుతుంది.", language="te-IN", tts_provider="gnani", tts_model="timbre-v3.0")
    assert "undocumented_audio_tag" in bad.hard


def test_english_number_words_in_indic_reply_are_flagged():
    result = check_reply("Split AC కి five hundred ninety nine rupees అవుతుంది.", language="te-IN",
                         tts_provider="sarvam", tts_model="bulbul:v3")
    assert "english_number_words_in_indic_reply" in result.warn
