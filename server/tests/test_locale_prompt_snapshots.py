"""B8: every advertised locale gets one dedicated spoken pack in final voice instructions."""
from server.prompts.agent_voice_rules import normalize_compile_language, spoken_pack_for

_ADVERTISED = (
    "te-IN",
    "hi-IN",
    "ta-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "bn-IN",
    "gu-IN",
    "pa-IN",
    "en-IN",
    "en-US",
)


def test_all_advertised_locales_have_distinct_spoken_packs():
    packs: dict[str, str] = {}
    for code in _ADVERTISED:
        lang = normalize_compile_language(code)
        pack = spoken_pack_for(lang)
        assert "--- SPOKEN LANGUAGE" in pack
        assert lang in pack or lang.split("-")[0] in pack.lower()
        packs[lang] = pack
    # No silent Hindi pack substitution for south-Indian locales.
    assert packs["ta-IN"] != packs["hi-IN"]
    assert packs["kn-IN"] != packs["hi-IN"]
    assert "Speak natural Tamil" in packs["ta-IN"]
    assert "Speak natural Kannada" in packs["kn-IN"]
