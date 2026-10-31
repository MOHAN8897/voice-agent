# Call stack and integration alignment

Checked 24 October 2026. These changes cover call admission, Gemini/Sarvam text adapters, speech selection, profile persistence and the shared integration gateway. No production configuration, saved tenant selections, billing rates or database schema were changed by running this work.

## Selected stack contract

An admitted call keeps its exact tier, provider, model, transport and voice. Disabled providers, incompatible transports, invalid voices, missing prices and failed model requests produce explicit errors. They do not select another provider, another model or a parent tier. Defaults apply when a choice is absent; they do not repair an explicit invalid choice.

Server-owned composed profiles resolve independently of unrelated Test Studio preferences. Native audio profiles use the native voice pipeline, including custom tiers, and do not require inactive standalone speech adapters. Unknown custom tiers require their own persisted configuration and price. Selected voice aliases and profile revisions must remain valid.

Call-start stack, instructions and pricing checks finish before replacing an existing session. Starts for one session are serialized within the process. A different tenant's session cannot be superseded. The existing prepared native greeting and its original session remain attached to the connected call.

Startup hydrates persisted configuration without activating profiles, approving test evidence or rewriting rates. Saving a profile versions its own price and configuration; it cannot overwrite an approved global billing-rate row. Missing or nonfinite FX and invalid custom prices fail admission rather than using invented rates.

## Model and tool protocols

Sarvam Conversations uses Chat Completions V1. Sarvam 105B supports V1/V2; the currently documented open-weight models use V2. Unknown model/transport combinations are rejected. These mappings follow [Sarvam's Chat Completion documentation](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview).

Gemini text calls use GenerateContent function declarations and matched function responses. Complete signed model parts, function names and identifiers survive the tool round trip. Newer Gemini models retain thought signatures; older models use a forced response function when structured speech and tools cannot share a JSON response mode. See [Google's GenerateContent function calling guide](https://ai.google.dev/gemini-api/docs/generate-content/function-calling.md) and [thought-signature requirements](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures).

Both text providers advertise tenant-authorized tools and execute through the same gateway. Tool output stays untrusted data. Speculative speech is buffered until an action result is available. Interrupted, malformed, oversized or duplicate action batches cannot cause speculative execution. Durable write claims prevent the same action from being repeated after a timeout or a repeated model request. Gateway proxy headers follow [Nango's proxy API contract](https://docs.nango.dev/reference/api/proxy/get).

The ordinary HTTP brain endpoints now enforce authentication and active-call ownership before model or integration access. They use the admitted session and language, and tenants cannot override the locked script. Browser starts resolve the saved agent profile on the server and use tenant-bound session identifiers. Stop, finalization and session-clear operations verify ownership. Signed Dev Portal Test Studio access remains supported. A failed stop does not erase live memory or return a false success.

## Speech transport alignment

Gemini unary and streaming synthesis make one request against the selected model. Quota, transport and empty-audio failures do not try another model. Live/text models are not advertised as standalone streaming TTS. The transport distinction follows [Google's GenerateContent speech-generation guide](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation).

Sarvam model/voice validation is shared by profiles, admission, the adapter and TTS configuration. Bulbul v2/v3 short names and v4 persona IDs have separate catalogs. The checked-in v4 catalog contains 222 documented IDs; invalid v4 voices cannot downgrade to v3. The published v4 persona roster does not cover Malayalam/Odia, so those selections are rejected. Catalog sources: [Bulbul model guide](https://docs.sarvam.ai/api/getting-started/models/bulbul) and [official voice roster](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices).

Composed model/speech failures report a failed selected service and terminate that session. They do not label the failure as unclear caller speech, retry an unconfirmed integration or keep a broken conversation running. Provider error bodies are not copied into these error responses or logs.

## Verification and limits

All 458 regression tests passed across 39 modules. The suite covers model-native tool transport, actual adapters through the authorization router and mocked gateway HTTP, SQLite-backed write audits, repeat-write suppression, foreign-agent denial, admission ordering, tenant ownership, custom pricing, configuration preservation and prepared greeting reuse. Transport tests use mock HTTP responses. No live calls, paid model requests or writes to a connected customer's integration were performed.

The stack security scan passed with zero findings across the 28 affected production paths. An initial full-repository scan flagged the invoice module's XML escaping import. During push verification this was replaced by equivalent `html.escape(..., quote=False)` string escaping. The required full-repository scan subsequently exited successfully with zero findings across 1,357 targets. It retained two rule timeouts and partial TypeScript parsing warnings; these are coverage limitations, not suppressed findings. A follow-up scan of all 108 pending production source paths used a 60-second timeout, reported zero findings and no timeouts, and retained a partial TypeScript parsing warning. See `delivery-2026-10-24.md` for the broader validation and known baseline test failures.

Ruff passed for the new modules and focused provider/test paths. Repository-wide lint and whitespace findings in existing unrelated changes were not rewritten. Reticle was skipped because this change set is backend-only; no UI was edited for this audit.

Live staging calls, provider-account entitlements and every connected app's real credentials still require environment-level verification. These offline results establish routing, protocol, authorization and failure behavior, not external service availability. Machine-readable regression and security evidence is recorded under `.gravitas/sessions/stack-integration-alignment/`.
