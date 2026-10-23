# Natural language and speech delivery

Runtime prompts combine the approved business script, the selected locale's current language pack, and the capabilities of the **resolved speech model**. Tier names do not imply a provider: custom tiers use their admitted stack too. Prompt reuse is scoped to the call and keyed by script content/version, locale, tier/combination and selected LLM/TTS model.

The approved script remains the source of business facts, required questions and mandatory wording. Platform language sections are refreshed when rendering a new session, including older language-only brains. This does not rewrite stored tenant scripts or replace a prepared live session during a call.

## Language register

`server/prompts/spoken_locale_style.py` defines compact style anchors for all 12 supported locales: Telugu, Hindi, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Indian English, American English and British English. These anchors survive the compact-pack path used by actual calls and are also supplied to legacy native-audio prompts.

Indic packs use local grammar and native script for local words, with familiar English words in Latin script. Mixing follows the caller's comfort; there is no English-word quota. Each pack prefers everyday spoken forms and respectful pronouns without repeating honorifics or ceremonial acknowledgements. Telugu uses Telugu-English; Tamil uses Tamil-English/Tanglish. English packs use ordinary contractions and their selected regional style.

Examples illustrate register, not new business facts or questions the agent must ask. A natural-style toggle being off preserves approved wording without silently forcing a formal register. Unknown facts remain unknown; style examples cannot promise callbacks, saved details or completed actions without the permitted workflow and successful tool result.

These are implementation choices informed by provider guidance. Native-speaker listening checks are still needed to assess accent, pronunciation and perceived naturalness across every selected voice.

## Delivery by model

- **Gnani Timbre v3.0:** optional documented angle-bracket cues. Ordinary business speech stays mostly plain. The prompt suggests at most one useful cue per turn (`<pauses>`, `<slow>` or `<excited>`), before the phrase it modifies, in the selected locale. It discourages performative laughter, bodily noises and invented positive announcements. A cue has no closing tag and its effect ends at the next cue or the end of that synthesis input.
- **Gnani Timbre v2.5:** plain punctuated text. v3 audio cues are removed. Its selected voices use the v2.5 catalog instead of being remapped through the v3 catalog.
- **Sarvam Bulbul v3:** plain text with native-script mixing and punctuation; pace/temperature use API configuration.
- **Sarvam Bulbul v4 Flash:** plain text with native-script mixing and punctuation; pace/pitch/loudness use API configuration.
- **Gemini TTS:** plain transcript; model-specific delivery metadata/instructions carry voice style. Default normal-speed delivery is warm and natural.
- **Native audio (Gemini Live/OpenAI Realtime):** direct natural speech without inline TTS cues. Separate stored TTS slots are inactive for this path.
- **Other or unknown models:** plain text by default. Tag capability must be explicitly implemented for a model before tags are retained.

The final speech sanitizer retains only exact, case-sensitive documented v3 cues when the actual provider/model is Gnani/Timbre v3.0. It removes unknown markup, unsupported cues, incomplete trailing cues and cues with no following speech. The completed-turn finalizer, prewarm, registry synthesis, PSTN speech boundary, and Gnani REST/WebSocket paths carry or enforce the model selection. Usage counts the sanitized text actually sent. Sentence buffering retains short replies such as `సరే.` and does not cut a multiword cue at its internal space.

## Provider references

Checked on 23 October 2026:

- [Gnani audio tags: supported model, exact spellings, scope and placement](https://docs.gnani.ai/api/TTS/tts-audio-tags)
- [Gnani model-specific voice catalogs](https://docs.gnani.ai/api/TTS/available-voices)
- [Gnani Timbre v3 launch and restrained use in sensitive contexts](https://www.gnani.ai/resources/blogs/introducing-gnani-timbre-v3-0-with-audio-tags-for-indian-languages)
- [Sarvam current speech best practices: native script, mixing and sentence chunks](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/best-practices)
- [Sarvam Bulbul v3 speech best practices](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/bulbul-v3-best-practices)
- [Google Gemini speech generation and delivery metadata](https://ai.google.dev/gemini-api/docs/speech-generation)

Gemini supports additional expressive mechanisms upstream; keeping its transcript tag-free here is an explicit application policy requested by the user.
