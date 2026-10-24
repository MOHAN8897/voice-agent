# TTS and tenant controls audit — 24 October 2026

## Provider voice inventory

Live catalogue discovery completed at `2026-10-24T18:04:33Z` (`23:34 IST`).
Credentials stayed in request headers and were not printed or committed. No
customer data or phone numbers were used for catalogue discovery.

- **Sarvam Bulbul v4 Flash:** the authenticated API returned **224 speaker IDs**.
  Its published voice table listed **222**, all present in the live response.
  The two additional IDs were `kangkana_as_conversational` and
  `mouchumi_as_conversational`. Their native language is Assamese, which is not
  currently accepted by the documented TTS language-code contract. The complete
  administrator catalogue includes them with a reason and disabled audition;
  tenant choices exclude unsupported voice/language combinations.
- **Google Gemini:** the paginated authenticated prebuilt-voice API returned
  **290 voices matching supported Indian locales**. The existing Gemini 3.8
  model mapping combines those with the **30 featured multilingual personas**,
  producing **320 entries**. Regional voices remain restricted to the existing
  supported model families and their published languages; no model allowance
  was expanded by this change.
- **Cartesia:** the paginated authenticated API returned **151 active public
  voices matching supported Indian locales**. Private, inactive and incompatible
  language/model rows remain excluded. Sonic 3.5 resolves to 151 available rows.
- **Gnani:** both published model voice tables were fetched successfully. The
  application uses the documented model and language mappings rather than
  guessing languages from voice names. A separate list-voices API was not used.

Sarvam does not document a standalone list-voices endpoint. Its best-practices
guide documents that an unrecognized speaker returns HTTP 400 with the live
speaker list. Discovery deliberately submitted a speaker outside the valid
persona-ID grammar, read that validation response, and generated no audio.
Incomplete, duplicate or unrecognized enums fail validation and retain the last
verified inventory. Other provider APIs follow all pages before replacing their
cached voice lists. The final refresh returned an empty error list.

## Why Telugu showed four voices

The complete provider response contains exactly these **four Telugu personas**:

- `kavitha_te_conversation`
- `kavitha_te_narration`
- `pooja_te_conversation`
- `tarun_te_narration`

The provider's roster-coverage guide also reports four Telugu speaker IDs.
There was no hardcoded four-item cap in the tenant list. The server and UI
filter by the agent's spoken language, so the other published native-language
personas are not silently relabelled as Telugu voices. The updated UI explicitly
states that all language-matching voices are included and explains how to browse
other languages. It displays safe total/per-language counts without provider or
internal voice identifiers. Administrator views show the complete provider
catalogue and identify rows that cannot be used with the configured languages.

Known voice order and existing aliases survive live refreshes even when the
provider returns a different order. Refresh callbacks now return their pending
requests and failure outcomes, preventing a success toast before requests finish
or after a handled catalogue failure.

## Code and local API boundaries

- `server/providers/voice_inventory.py`: provider discovery, complete enum and
  pagination checks, model/language validation, safe inventory expansion.
- `server/providers/catalog_data/voices.json`: bundled last verified inventory;
  v4 roster updated to the 224 IDs actually returned by the provider.
- `GET /api/dev/stack/catalog?refreshVoices=true`: authenticated administrator
  catalogue refresh; unavailable provider rows stay visible to administrators.
- `GET /api/voice-stacks/catalog?language=te-IN`: authenticated subscriber
  catalogue, opaque aliases, complete matching rows and safe inventory counts.
- `server/services/saas/voice_stack_profiles.py`: existing revision-checked
  alias resolution and read-through expansion; database profile assignments and
  revisions were not rewritten by catalogue discovery.
- `web/components/dev/PstnVoiceProfileWorkbench.tsx`: complete administrator
  catalogue, real provider voice identity, disabled unavailable rows.
- `voxly-ai/src/console/modules/agent-workspace/AgentVoicePanel.jsx` and
  `voxly-ai/src/console/modules/AgentStudioModule.jsx`: tenant language counts,
  complete scrolling list, awaited refresh and failure feedback.

## Executed regression checks

`python -m pytest server/tests/test_voice_inventory.py server/tests/test_three_tier_voice_profiles.py server/tests/test_profile_execution_alignment.py -q`

Result: **62 passed**, one existing Python `audioop` deprecation warning.
Coverage includes complete live-enum parsing, failure preservation, unsupported
language exclusion, stable aliases/order, 60 matching voices without truncation,
safe catalogue counts and exact selected voice/model resolution.

From `voxly-ai`, with `PLAYWRIGHT_SKIP_WEBSERVER=1`:

`npx playwright test e2e/voice-catalog-mapping.spec.js --reporter=line`

Result: **3 passed**. The browser checks cover scrolling and saving the sixtieth
voice, explaining a four-voice native roster against a larger catalogue without
vendor disclosure, and reporting a failed refresh without a success message.
These tests mock API responses. They do not substitute for an authenticated
Reticle verdict over the running application's real data.

`git diff --check` passed for the catalogue and UI files above.

## Official sources checked

- [Sarvam voice catalogue](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices)
- [Sarvam v4 Flash best practices, roster coverage and validation errors](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/best-practices)
- [Sarvam REST TTS API contract](https://docs.sarvam.ai/api-reference/text-to-speech/convert)
- [Gnani available voices](https://docs.gnani.ai/api/TTS/available-voices)
- [Google Gemini speech generation and featured voices](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Cartesia voice listing API](https://docs.cartesia.ai/api-reference/voices/list)
- [Cartesia model language compatibility](https://docs.cartesia.ai/build-with-cartesia/tts-models/older-models)

Provider documents disagree about some v4 delivery knobs. The platform knob and
runtime findings should be read together with the live validation and synthesis
evidence recorded separately in this audit.
