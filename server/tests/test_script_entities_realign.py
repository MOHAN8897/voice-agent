from server.brain.script_entities import realign_calling_script_for_session


def test_b1_telugu_realign_patches_opening_and_speak_line():
    script = """--- CANONICAL OPENING ---
After the callee speaks, say once (in the configured language):
Hello from English block.

Speak this way: English (US), clear and professional.

@language: te-IN
@opening_line: Namaskaram, nenu mee service team nundi matladutunnanu.
"""
    out = realign_calling_script_for_session(script, "te-IN", direction="outbound")
    assert "Namaskaram" in out
    assert "English (US)" not in out
    assert "te-IN" in out


def test_stale_language_pack_line_is_realigned_to_the_session_language():
    script = (
        "--- AGENT IDENTITY ---\nYou are Priya.\n\n"
        "--- LANGUAGE ---\nUse the selected en-IN language pack. Follow the platform language policy.\n"
    )
    out = realign_calling_script_for_session(script, "te-IN")
    assert "Use the selected te-IN language pack." in out
    assert "Use the selected en-IN language pack." not in out
