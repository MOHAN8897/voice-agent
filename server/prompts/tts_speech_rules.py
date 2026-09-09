"""
Spoken-output rules for LLM → TTS (Cartesia Sonic + Sarvam Bulbul).

TTS engines are NOT prompted like an LLM (no system prompt / free-text style brief).
Voice quality comes from:
1) LLM writing punctuated, speakable sentences (rules below)
2) Provider delivery knobs — Cartesia generation_config {emotion, speed, volume};
   Sarvam pace + temperature (see server/services/tts_voice_direction.py)

Sources:
- Cartesia prompting tips: well-punctuated prose; do not strip punctuation;
  end with . ? or !; normal capitalization; generation_config for delivery.
- Sarvam Bulbul v3: native Indic script + Latin English code-mix; keep
  punctuation for sentence splits; large digit runs prefer commas or spoken words;
  pace/temperature only (no SSML / system prompt).
"""

SPEECH_GRAMMAR_RULES = """SPOKEN GRAMMAR (mandatory — TTS reads your text aloud)
- Write complete spoken sentences with normal grammar. Always end each reply with . ? or !
- Use commas for natural pauses. Never omit periods, question marks, or commas.
- Capitalize sentence starts and proper nouns. Never ALL-CAPS ordinary words (TTS may spell them).
- No markdown, bullets, asterisks, hashtags, emoji, or raw JSON — engines read those aloud.
- Prefer one or two short phone sentences. Sound like a real caller, not a telegram.
- Indic words in native script (Telugu/Hindi); everyday English business words in Latin script is fine."""

# Cartesia Sonic: keep conventional written forms when possible; Indian money still as words.
CARTESIA_SPEECH_HINT = (
    "Cartesia Sonic reads punctuation for pacing — keep . ? ! and commas. "
    "End every reply with terminal punctuation. Delivery tone is set via generation_config, not a text prompt."
)

# Sarvam Bulbul: native script + punctuated sentences; avoid bare long digit strings.
SARVAM_SPEECH_HINT = (
    "Sarvam Bulbul needs punctuated sentences and native-script Indic words. "
    "Write Indian amounts as English cardinal words (`rupees fifty lakhs`), not bare digits. "
    "Pace/temperature are API knobs only — there is no TTS system prompt."
)
