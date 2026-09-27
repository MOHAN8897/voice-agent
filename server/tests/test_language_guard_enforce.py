from server.realtime.language_guard import enforce_output_language_script


def test_te_strips_devanagari_hindi_leakage():
    text = "మాట్లాడొచ్చా? में इंटरेस्टेड हैं?"
    out = enforce_output_language_script(text, "te-IN")
    assert "में" not in out
    assert "మాట్లాడొచ్చా" in out
