"""PSTN listening backchannel — phrase pick + eligibility."""
from types import SimpleNamespace

from server.services.pstn_backchannel import (
    MIN_WORDS,
    PstnBackchannelController,
    pick_backchannel_phrase,
)


def test_pick_backchannel_phrase_by_language():
    en = pick_backchannel_phrase("en-IN")
    te = pick_backchannel_phrase("te-IN")
    assert en in {"Hmm.", "Mhm.", "Right.", "I see.", "Okay."}
    assert te in {"Hmm.", "Mhm.", "Aha.", "Sare.", "Avunu."}


def test_min_words_threshold():
    from server.services.transcript_gate import effective_word_count

    assert effective_word_count("hi") < MIN_WORDS
    assert effective_word_count(" ".join(["word"] * MIN_WORDS)) >= MIN_WORDS
