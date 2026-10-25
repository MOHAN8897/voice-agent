# Voice agent reliability and prompt consistency — implementation plan

Date: 25 October 2026, IST. Baseline: branch `working-app-22-10-2026`, commit `3aed4cc`. Status: **proposed implementation; application code unchanged**.

This plan covers agent creation, script generation, published brains, session prompt selection, multilingual intent, request recovery, conversation state and hangup. It builds on the existing extract/write/review pipeline, immutable publication, call context, provider adapters and close executor. It does not propose replacing the voice platform or adding a second always-on LLM to every turn.

The objective is measurable reliability across every supported locale and eligible voice stack. No prompt can guarantee perfect understanding or eliminate provider failures. The implementation must prevent uncertainty or recoverable failure from silently turning into a normal goodbye, and must preserve an honest, bounded failure path when service cannot continue.

Only this planning document was created for this request. No application source, tests, prompts in the database, active agent publications, provider assignments or production settings were changed. No calls were placed. Architecture method: Atlas; evidence and scope checks: Gravitas. Planning depth: deep; dependency context; read-only investigation; no delegation.

## 1. What the recheck established

### Confirmed regression and call evidence

The last two audited calls ended after `IncompleteTurnError(finish_reason='length')`, with no usable reply and no retry. The composed voice error handler then spoke the standard farewell and disconnected with an unresolved caller need. One caller turn was affirmative; the other asked for wedding cards and their pricing.

Commit `3aed4cc` made `CONFIRM_ORDER_TOOL` available to every active composed agent. That selects an existing first-tool-request branch which calls the adapter directly. It bypasses `_stream_composed_turn`, including its token floor and recovery. The prior `fa2228f` wrapper had a 640-token floor; the latest wrapper configures 1,280 but this initial tool branch does not reach it. The current default request reconstructs to 320 output tokens. Exact historical HTTP bodies were not archived, so 320 remains a reconstruction, not a historical measurement.

Evidence: [initial tool request](<D:/voice agent/server/call/live_turn_orchestrator.py:1028>), [unconditional order tool](<D:/voice agent/server/call/live_turn_orchestrator.py:1313>), [budget/retry wrapper](<D:/voice agent/server/call/live_turn_orchestrator.py:1158>), [failure-to-close path](<D:/voice agent/server/services/pstn_voice_core.py:2716>), [prior call audit](<D:/voice agent/artifacts/call-quality-review/2026-10-25-hangup-audit.md:1>).

### Existing architecture worth keeping

- Subscriber creation already performs permission and tenant resolution, language availability checks, clarification, and idempotent build-request handling when a request ID is supplied. Preserve this behavior. [Creation](<D:/voice agent/server/routes/app_agents.py:121>)
- The employee pipeline already extracts source-backed facts, writes a business script, reviews/repairs it, validates it and constructs an agent specification. Improve this pipeline rather than adding another competing generator. [Extraction](<D:/voice agent/server/brain/employee_script_pipeline.py:160>), [generation](<D:/voice agent/server/brain/employee_script_pipeline.py:215>)
- Reviewed publication already compares a revision and commits a compiled snapshot atomically. Keep this as the publication boundary. [Publication](<D:/voice agent/server/brain/business_brain_store.py:229>)
- Call startup already freezes a brain and resolved voice stack and can adopt the dial-time prepared brain. Preserve this identity through answer. [Call admission](<D:/voice agent/server/call/call_lifecycle_service.py:239>)
- Composed prompts already have a call-owned cache. Strengthen the manifest and ownership checks, rather than introducing a global cache of personalized prompts. [Composed prompt](<D:/voice agent/server/services/composed_voice_session.py:35>)

### Additional gaps found during this recheck

1. **Preview/runtime divergence:** `build_live_prompt_for_call` has a native audio branch, then uses the realtime text builder for all remaining pipelines. A composed live call actually uses `composed_system_prompt`. A composed preview can therefore show the wrong assembly and provider. [Preview](<D:/voice agent/server/call/call_prompt_preview.py:51>), [actual runtime](<D:/voice agent/server/call/live_turn_orchestrator.py:360>)
2. **Validation coverage and enforcement:** the saved brain contains a Telugu session plus `Use the selected en-IN language pack`, yet current `validate_rendered_brain` returns `[]`. Separately, a call-admission path catches rendered-brain validation errors, logs a warning and proceeds. Both require correction. [Validator](<D:/voice agent/server/brain/brain_prompt_validate.py:9>), [warning-only admission](<D:/voice agent/server/call/call_lifecycle_service.py:288>)
3. **Language-sensitive request loss:** current `meaningful_remaining_request` returns false for `why`, `ధర` and `ఎంత` because of its four-character cutoff. Intent cannot be defined by English word length. [Request guard](<D:/voice agent/server/call/close_decision.py:125>)
4. **Asymmetric closing contracts:** composed responses provide evidence and remaining-request fields; the native `request_end_call` tool requires only a reason. Native and composed adapters must normalize to a common server-side authorization contract without pretending their transports are identical. [Composed schema](<D:/voice agent/server/call/live_turn_schema.py:14>), [native tool](<D:/voice agent/server/realtime/hangup_tools.py:33>)
5. **Existing tests expose a model-selection contract disagreement:** 222 passed, 3 failed in the focused recheck. The three cases expect a missing/invalid explicit Gemini model to be filled in, while current native transport validation rejects it. Define the intended contract before implementation; do not restore silent switching to make tests green. [Test](<D:/voice agent/server/tests/test_primary_script_flow.py:67>), [resolver](<D:/voice agent/server/realtime/models.py:221>)

These supplement the earlier reproduced affirmative-as-refusal and unpunctuated-Telugu-question defects. They are not all established causes of the two historical failures.

## 2. Required end behavior

The following examples are acceptance requirements, not new business facts:

- “Yes, I am interested” after the opening: acknowledge, follow the next useful script objective, stay connected.
- “I do not want visiting cards, but I want wedding cards”: preserve the wedding-card request; a product-specific rejection does not reject the entire conversation.
- “Do you make wedding cards?” with no question mark: treat it as a service inquiry. If availability is not in approved facts or a successful tool result, say it is unknown. Do not invent availability, use the visiting-card price, or promise an unavailable callback.
- “Why?”, “ధర” or an equivalent short utterance: use the previous question and conversation context; answer or clarify. Character count alone never authorizes close.
- “No thanks, I do not need this” with no other need: acknowledge and close politely. Do not require repeated refusals or a minimum number of sales turns.
- “Do not call me again”: end promptly and record stop-contact separately from a one-call decline.
- “Not now”: follow the permitted busy workflow. Offer a callback only when the business permits it and the system can support it; wait for the answer instead of inventing consent.
- “Okay” or “thanks”: an acknowledgment. It only confirms a close if the immediately preceding explicit close question and already-proven outcome make that meaning unambiguous.
- “Wait, one more question” before disconnect is committed: cancel the pending conversational close and answer. Do not replay the opening or farewell.
- LLM `length`, timeout or malformed output before speech: recover within a bounded deadline; do not treat it as customer refusal.
- Exhausted model recovery: explain that the agent could not complete the response; use a permitted fallback or an honest technical close. Never claim the customer's needs were completed.

## 3. Target architecture and trust boundaries

The lifecycle will be:

**Brief and clarification → source-backed AgentSpec → reviewed business script → validated published artifact → authorized call-session snapshot → selected transport renderer → turn interpretation and response → server close authorization → farewell playback → final authorization check → disconnect.**

The business specification owns facts, products, objectives, required disclosures, allowed next steps and genuine business constraints. A single versioned platform policy owns safety, privacy, truthful tool claims, language selection, turn-taking and call-ending behavior. A locale pack owns language-specific presentation. The selected transport adapter owns protocol differences. The server owns actual tool execution and disconnection.

Caller speech, uploaded briefs, contact fields, retrieved records and tool outputs remain data at their respective trust boundaries. They cannot select another tenant, override platform safety, add tool permissions or create a hangup authorization merely by containing an instruction.

### Internal contracts to define before parallel implementation

Extend existing models where possible; the names below describe responsibilities, not a requirement to create six new services.

1. **AgentSpec:** version, identity, selected locale, role/direction, product-scoped facts with provenance, conditional workflow objectives, required/optional fields, permitted next steps, explicit unknowns, tool prerequisites and completion conditions. Include author revisions and clarification provenance. A script is a rendering of this source, not a new source of truth.
2. **Compiled artifact manifest:** specification and business versions; platform-policy, locale-pack and compiler versions; stable section IDs with hashes; mandatory rule/fact coverage; selected modality; token estimates; checksum; validation and semantic-review results. Store business content separately from platform-owned instruction text.
3. **Call-session snapshot:** tenant, agent, call and session ownership; admitted locale, direction, channel, mode and voice-stack revision; exact artifact and rendered-prompt checksum; authorized tool-set version; contact-data checksum; opening state and prepared-session owner. Immutable configuration for the lifetime of a call; dynamic conversation state is separate.
4. **Turn interpretation:** caller-turn sequence, complete current utterance, relevant previous question, speech/finality status, intents, scoped refusal, new/open requests, corrections, opt-out, completion acknowledgment and evidence spans. Store observable facts and short labels, never hidden chain-of-thought. Do not trust a self-reported confidence score as proof.
5. **Close authorization:** server-approved reason, caller-turn/close epoch, unresolved-request state, allowed farewell, contact preference and expiry. Authorization is revocable before provider disconnect and consumed once. Operational failures use a separate cause, not a fabricated caller intent.
6. **Provider request/result contract:** provider/model/mode capability validation; actual output budget and reasoning setting; attempt and deadline; whether any speech or side effect occurred; normalized finish/error category; actual or unknown usage; tool execution identity and result proof.

Keep public APIs compatible during the first repair. Any later change to subscriber-visible routes or response contracts must be additive/versioned and reviewed before activation. Internal native tool schemas can evolve through versioned adapters while accepting older prepared sessions safely.

## 4. Work package A — lock regressions and contracts first

**Priority:** immediate. **Depends on:** none.

Implementation:

- Turn the two archived call utterances into redacted, deterministic fixtures with expected continue/answer behavior. Include the exact mixed product refusal and the elliptical affirmative, not just clean English translations.
- Add a route-level failure test for the initial tool-offered request; testing `_stream_composed_turn` alone is insufficient.
- Add wrong-close proposals quoting affirmative text and product inquiries. Assert rejection even when `remaining_request` is incorrectly empty.
- Add short-request and missing-punctuation cases in each supported locale.
- Lock the explicit-provider/model rule: a supplied invalid or missing model in an explicit stack fails before a billable call. If the product intentionally permits omitted defaults, resolve a valid default at configuration/admission, record it in the snapshot, and never change the live model silently.
- Reconcile the three failing model-selection test cases with this documented contract, preserving tests that forbid provider substitution. Record any changed assertion and its rationale; do not delete coverage to get a green result.

Acceptance: each actual defect has a failing regression before its implementation; all existing failures have an explained disposition. No test treats an accepted wrong close as successful product behavior.

Files: existing tests for finish-reason recovery, composed transport, close decision, primary script flow, runtime prompt contract and employee generation. Add new cases beside the relevant existing tests rather than creating a separate fake voice framework.

## 5. Work package B — repair request budgets, recovery and tool selection

**Priority:** immediate. **Depends on:** A.

Implementation:

- Route ordinary text generation, initial tool selection and post-tool response through shared request-policy normalization. Keep their side-effect semantics distinct.
- Apply the same configured 1,280 first-attempt floor and bounded 2,560 retry ceiling to the affected composed profile initially, subject to selected model/account limits. A larger explicit valid budget must never shrink. These are rollout settings to validate, not universal optimal values for every provider or language.
- Account for the entire output envelope: control fields, spoken response, allowed memory operations, tool arguments and any configured reasoning allowance. Keep the spoken answer brief without restricting the whole envelope to a 1–2-sentence token budget.
- Preserve explicit Sarvam V1 reasoning disablement where already configured. Test the serialized request, not just a Python variable; log the effective setting without logging reasoning content. Do not assume every provider uses the same reasoning parameter.
- Make tools conditional on both business permission and actual authorized capability. `CONFIRM_ORDER` is offered only for an applicable order workflow. Keep its proof checks when enabled; globally deleting the tool would reintroduce unsupported order claims.
- Retry `length` once before speech or side effects, with a materially larger budget and the same selected model. Track one recovery allowance across request retry and the reply watchdog so the two cannot multiply requests.
- If partial speech already played, preserve it and continue only when a safe continuation can be verified. Never replay the opening, an order, a completed sentence, a farewell or a tool side effect.
- If a tool ran, keep its durable result and idempotency key. Retry only the final response when safe; reconcile uncertain tool execution through the durable execution record rather than issuing the write again.
- Treat safety rejection, invalid credentials, invalid model/config and unrecoverable protocol failures according to their category; do not apply a generic same-request retry loop.
- Keep bounded connect/read/request deadlines, cleanup and cancellation. An exhausted failure enters a localized honest technical path, records the initiating cause and cannot become `not_interested`, `goal_complete` or a successful order.
- Capture final usage when a provider sends it after the terminal chunk, within a bounded drain. Missing usage is unknown, not zero.

Acceptance: the last-two-call failure injection recovers without a normal goodbye; all three request branches use the effective policy; side-effect count remains exactly one; the same selected model remains pinned; exhausted failure produces one honest technical message and a categorized close.

Files: `server/call/live_turn_orchestrator.py`, `server/providers/llm_protocol.py`, selected LLM adapters including `sarvam_llm.py`, `server/services/pstn_voice_core.py`, reply-watchdog and failure-diagnostics helpers. Reuse the existing recovery wrapper and registry.

## 6. Work package C — strengthen script generation and agent creation

**Priority:** high. **Depends on:** A and internal AgentSpec contract.

Implementation:

- Keep the existing extract → write → review stages. Extend extraction to represent which product a price/refusal condition refers to, which fields are required for which action, and what success actually means.
- Preserve exact business names, amounts, currency, conditions, negations and mandated disclosures. Clarifications have stable IDs; a user correction supersedes an earlier fact with provenance. Explicitly unavailable facts stay unknown and are not asked again.
- Expose conflicts and material missing requirements before publication. A specific missing price can be marked unavailable; do not prevent every agent from being created merely because a nonessential commercial detail is unknown.
- Generate a business workflow with conditional objectives and stable IDs. Mark objectives answered, skipped, inapplicable or pending during a call. Do not turn optional qualification into a checklist or force a sales path on support.
- Replace generated hangup instructions and generic farewell paragraphs with business completion conditions. The customer-facing script may show an example of the platform close for clarity, but the runtime business section must not gain a second farewell policy.
- Express unknown-product handling explicitly: answer from approved facts, state uncertainty, and offer only a permitted and available next step. No wedding-card availability or price may be inferred from visiting-card facts.
- Perform deterministic identity/numeric/provenance checks plus bounded semantic review against the structured specification and platform policy. The review must identify the conflicting rule IDs and source spans; its `passed` flag alone is not the publication gate.
- Validate opening and exact spoken content across all locales, preserving names in their supplied form; do not require a guessed transliteration of a proper name. Do not rely on Latin-script identity checks only for English agents.
- Make the subscriber employee builder, developer instructions/regeneration and existing manual-script publication feed the same normalized specification and validation contracts. Keep route-specific authorization; do not combine their access levels. Hand-authored mandatory wording remains preserved or returns an explicit conflict requiring review.
- Preserve idempotent creation, unfinished-draft recovery, revision checks and atomic publication. Ensure an agent is callable only when the reviewed publication and compatible stack are ready; a retained failed draft must not masquerade as a ready agent.

Acceptance: the same brief/settings yield semantically equivalent facts and workflow across entry points; no invented capabilities or prices; unknowns remain unknown; repeated creation requests do not create extra agents; failed review never activates a partial artifact.

Files: `server/brain/employee_script_pipeline.py`, `agent_spec.py`, `brief_contract.py`, `agent_script_compiler.py`, `server/services/saas/employee_brain_build.py`, `server/routes/app_agents.py`, existing instructions/publication adapters, `compiled_brain_service.py` and `business_brain_store.py`.

## 7. Work package D — one contradiction-free platform policy

**Priority:** high. **Depends on:** A and C's rule-ownership contract; can build alongside C after contracts settle.

Implementation:

- Give platform rules stable IDs and versions for language, opening ownership, answer-first behavior, truthful actions, refusal, goal completion, communication barriers and close timing.
- Render these rules from one policy definition into composed prompts and native tool/session instructions. The transports may need different wording, but they must implement the same allowed transitions and reason meanings.
- Remove duplicated obsolete instructions from persisted embedded platform blocks through a validated compatibility renderer. Do not append a new footer and hope it wins over contradictory saved text.
- Validate the complete final artifact, not just selected headers: detect `Use the selected en-IN language pack` in a Telugu session, conflicting opening timing, model-owned farewells, invented callbacks and incompatible exact disclosures.
- Distinguish harmless business examples from actual conflicting directives. Preserve approved facts and mandatory wording; if safely separating old business text from embedded platform text is uncertain, mark the version as requiring review rather than silently deleting content.
- Retain one answer-first rule, one brief-turn rule and one close rule. No intentional padding for cache eligibility. Current `_ensure_cache_floor` already returns without adding padding; preserve that behavior.
- Add semantic scenario checks for contradictions a text linter cannot prove. Deterministic markers and regex checks are a fast layer, not a complete language-understanding solution.
- Reject invalid artifacts before dialing or opening a billable session. Validate prepared bundles before dial; admission verifies their checksum/validation status rather than recompiling or replacing their live session at answer.

Acceptance: exactly one effective policy owner per rule, one locale pack, one opening contract and one close contract. The archived contradictory brain fails with precise errors. Publication, preview, prewarm and admission all agree on validity.

Files: `server/brain/compiled_brain_artifact.py`, `brain_prompt_validate.py`, `sections.py`, compiler platform-rule generation, `server/prompts/agent_voice_rules.py`, locale/continuity policies and native instruction adapters.

## 8. Work package E — minimal, correct brain for each call/session

**Priority:** high. **Depends on:** C/D artifact contracts. B does not wait for this refactor.

Each admitted session will receive only:

1. Mandatory platform safety/privacy/action-truth rules.
2. The single admitted primary locale's speech/register rules.
3. That agent's published identity, applicable workflow, approved facts and constraints.
4. The selected channel, direction and mode rules—for example outbound versus inbound or permitted voicemail.
5. The actual authorized capabilities/tools and the selected transport's delivery rules.
6. A bounded, separate dynamic context containing completed objectives, pending needs, caller corrections, tool results and necessary contact values.

Exclude other agents' content, other language packs, draft/obsolete rules, inapplicable workflows, unconfigured tools, unused provider instructions, historical audit text, generator prompts and duplicate pinned copies. Do not exclude mandatory privacy/disclosure constraints or facts necessary to answer the caller.

Implementation:

- Build a deterministic section-selection manifest from the admitted snapshot. Select by stable IDs and scope, not brittle heading regexes or phrases in free text.
- Resolve tenant, agent, campaign/contact and authorized session override provenance before selecting content. Include tenant and agent ownership in every session/cache lookup and verify compatibility with the chosen published version. This is a required invariant, not an assertion that a cross-tenant exploit has been demonstrated.
- Freeze the artifact, platform/locale policy versions, voice stack, direction, tool schema and personalization at call admission/dial preparation. Mid-call edits affect future calls only. Any permitted emergency revocation is an explicit server action, not silent prompt drift.
- Keep essential business rules and active workflow invariant. For a genuinely large knowledge base, retrieve only relevant approved facts as untrusted data with provenance and an unknown fallback; do not add a retrieval subsystem for this small current script. Never delete late mandatory facts merely to meet a cosmetic token target.
- Measure system instructions, tools/schema, history, memory and reserved output separately. Validate the combined context limit before requests. Reduce duplicate boilerplate, compress bounded old conversation state or return a clear preflight error; never arbitrarily truncate a required rule or set output budget to the remaining few tokens.
- Use the exact same renderer for runtime and preview. Preview reports artifact and render checksum, locale, included section IDs, tool list and token breakdown. Private infrastructure fields stay privileged; tenant surfaces use generalized labels.
- For stateless composed requests, send the required static instructions and bounded current state on each request, using supported prefix caching when available. A brain ID alone does not supply instructions to a stateless API.
- For native stateful audio, supply the selected instructions/tools at session setup and send bounded conversation/tool events afterward. Do not create a cold session or resend the whole script on every turn. Do not force a composed JSON response schema onto a native audio API that does not support it.
- Bind the prepared opening, personalized brain checksum and live-session ownership to the tracking/carrier ID handoff. Consume the greeting once. Preserve the hot primary Live session, fast-answer behavior and owner routing; a lost session fails clearly.
- Record `opening_prepared` separately from `opening_delivered`. Mark delivery only after the actual media handoff, then send the existing silent opening-delivered note. A later hello or affirmative never replays it.

Acceptance: preview and actual request render checksums match; one locale/policy set; tenant A/agent A cannot get B's artifact; two simultaneous calls with different contacts remain isolated; a publication during a call does not mutate its prompt; prewarm and answer adopt the same artifact/session; empty or conflicting configuration fails before dial.

Files: `compiled_brain_artifact.py`, `compiled_brain_service.py`, `server/call/call_brain_lock.py`, `call_context.py`, `call_lifecycle_service.py`, `call_prompt_preview.py`, `server/services/composed_voice_session.py`, `pstn_prewarm.py`, native session renderers and the existing carrier bridges. Use the existing immutable snapshot rather than a second independent publication store.

## 9. Work package F — multilingual intent and script progress

**Priority:** high. **Depends on:** A and Turn interpretation contract; consumes C/E as available.

Current registry coverage is 12 locales: `te-IN`, `hi-IN`, `ta-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, `pa-IN`, `en-IN`, `en-GB`, `en-US`. All have spoken packs. Platform enablement and the chosen provider's STT/LLM/voice capabilities still decide which combinations are callable. [Registry](<D:/voice agent/server/config/constants.py:94>)

Implementation:

- Separate caller meaning from response language. Understand supported code-mixing and transliteration; answer in the admitted primary locale. Do not mistake a loanword, name or accent for a language barrier.
- Use the complete utterance and relevant preceding question. A short affirmative after an introduction and an affirmative after a completed booking-confirmation question are not the same event.
- Represent multiple intents and scoped rejection: declining product A while requesting B; unavailable now while permitting a later call; correcting a previous negative; withdrawing an earlier callback.
- Track open questions and requested tasks on the server, with IDs and resolution status. Do not depend solely on a model setting `remaining_request=''`. Keep business unknowns separate from answered requests and successful actions.
- Remove the minimum-character assumption for open requests. Use structured request status; normalize Unicode and preserve the original transcript/evidence without destroying native script.
- Use language packs and multilingual test corpora for lexical guard cues, but do not treat an expanding refusal regex list as universal semantic understanding.
- For a proposed non-explicit close where meaning remains uncertain, ask one short clarification or use a bounded semantic verification step. The normal main response already supplies interpretation; do not add a second serial model call to every acknowledgment. A verifier receives only the minimum relevant utterance/context, returns labels and evidence, and cannot directly disconnect.
- Validate evidence provenance and polarity. A matching quote proves where words came from, not what they mean. Self-reported high confidence and a tool-origin flag do not make a refusal true.
- On interruption, answer the new request first, then return to the next applicable unfinished objective. Do not repeat answered questions, insist on optional fields or restart the pitch. Record corrections immediately; do not retain superseded product/price/consent state.

Acceptance: every enabled locale passes the same semantic scenarios, including native spelling, punctuation removal, code-mixing, phonetic Latin script, negation and corrections. Add locale-specific counterexamples, not only literal translations of English tests. Previously collected details remain correct across interruptions.

Files: `server/call/close_decision.py`, `end_call_validate.py`, `live_turn_schema.py`, `live_turn_orchestrator.py`, bounded memory helpers, locale packages and both voice loops. Use the same server interpretation/authorization policy through transport adapters.

## 10. Work package G — human-appropriate, revocable closing

**Priority:** high. **Depends on:** A/F contracts; B repairs the failure path first.

Implementation:

- Define explicit conversational close states using the existing controller/executor: active → proposed → authorized → farewell playing → ready to disconnect → disconnected. Add only the missing internal state/events; avoid a parallel lifecycle state machine.
- Accept a conversational close only for a supported, validated reason: clear call-end request, clear overall decline with no alternative need, stop-contact, completed applicable objective/agreed next step with real proof, or applicable safety/abuse policy.
- A price/service/product question, affirmative, soft objection, unknown answer or simple acknowledgment cannot by itself authorize close. Unknowns default to continue/clarify. Do not use model-emitted goodbye as independent proof that the caller is done.
- Normalize reason and contact preference consistently across composed JSON, `end_call`, `request_end_call`, `call_action`, fallback repair and the controller. Preserve the difference between refusal, explicit stop-contact and technical failure. Generate reason allowlists from one internal definition.
- A native close tool can arrive before its corresponding transcript. Hold that proposal for a bounded evidence/finality window and bind it to the correct caller turn; never validate it using an older utterance or treat `tool_sourced` as caller consent. If usable caller evidence is unavailable, preserve the call and obtain one concise clarification when necessary. Do not introduce an unbounded transcript wait or a cold replacement audio session.
- Goal completion requires actual satisfied objectives and any required tool result; saved contact details or an agent-written promise alone do not establish it. Avoid asking an extra ceremonial confirmation when the caller has already clearly agreed.
- Wait for the caller to finish before authorizing and again before disconnect. Bind authorization to the latest complete turn and close epoch; reject stale tools, delayed transcripts and old generation callbacks.
- Platform-owned farewell is spoken once after approval. Native audio uses the existing session's authorized close mechanism; composed uses the configured voice. TTS completion, model generation completion and carrier playback completion are different events.
- Wire `can_disconnect` into the composed path and preserve pending speech until the final decision. A substantive new request before commit revokes close authorization, cancels remaining farewell audio if possible and resumes at the current objective. A backchannel alone does not reopen or interrupt the farewell.
- Define a short, configurable post-playback listen interval for ordinary goal-complete closes and verify it with real media timing. Initial trial value: approximately 500 ms, subject to end-to-end evidence. Explicit stop-contact should remain prompt; do not add a blanket long wait to every refusal.
- Serialize the final check and provider-hangup commitment through a close epoch/atomic guard. Once the remote disconnect is committed, record it accurately; do not pretend a later transcript can revive the call.
- Keep operational closes for provider failure, exhausted silence recovery, max duration and user transport disconnect separate. No unbounded silent or billable call; one authorized presence check for genuine silence, not repeated prompts over active speech or tool work.

Acceptance: no wrong close for the call fixtures; exactly one farewell and one provider hangup; caller resumption before commit cancels ordinary close; stale tool/duplicate-final races cannot close another turn; explicit stop-contact remains honored; no DNC change is created by a model outage.

Files: `end_call_validate.py`, `close_decision.py`, `call_controller.py`, `close_call_executor.py`, `natural_hangup.py`, `hangup_judge.py`, `callback_close.py`, native hangup-tool adapters and both PSTN voice loops.

## 11. Work package H — turn-taking and hearing the full user need

**Priority:** high; preserve existing invariants rather than retuning broadly. **Depends on:** A; integrates with F/G.

Implementation:

- Preserve Sarvam VAD defaults: `high_vad_sensitivity=False`, threshold `0.55`, minimum speech 300 ms, silence 600 ms; preserve the 350 ms playout-onset grace and energy floor during active speech.
- Keep backchannel acknowledgments from truncating active speech. A standalone yes can answer a question once the agent has finished; the same nod during playout should not restart generation.
- Keep explicit halt commands effective. Other interruption requires the existing sustained substantive-utterance checks, with locale-aware lexical counting that does not equate whitespace tokens with meaning in every language.
- Coalesce genuine fragmented utterances without indefinite waiting. Avoid cancel/relaunch loops on repeated identical finals; associate partial/final revisions with one caller turn.
- Preserve echo guards, playout generations and late-callback protections while testing quiet callers, background noise, delayed finals and overlapping audio.
- Measure time separately for STT finalization, coalescing, model response, tool wait, first TTS audio and carrier playback. Optimize the measured stage instead of describing all delay as model thinking.

Acceptance: the latest call's affirmative can become a normal reply rather than a repeated cancellation; backchannels do not clip the agent; a meaningful alternative need is captured; recovery does not overlap stale audio or lose the pending utterance.

Files: `pstn_voice_core.py`, `pstn_realtime_voice_core.py`, transcript/backchannel/echo helpers, `pstn_turn_tts.py` and carrier playback adapters. Native activity/interruption events retain their own protocol; do not apply Sarvam knobs to a native session that has no Sarvam STT stage.

## 12. Work package I — diagnostics, honest outcomes and operator review

**Priority:** alongside B/E/G. **Depends on:** their event contracts.

Implementation:

- Privileged call review shows the artifact/render checksum and versions, selected locale, enabled capabilities, request attempt/budget, finish/error category, interpretation labels, close decision/rejection code, playback timings and actual disconnect cause.
- Separate root failure, conversational end reason and transport event; a later `ws_disconnect` must not erase the preceding failed-reply cause.
- Capture sanitized model control outputs and exact evidence references where authorized. Do not log secrets, raw reasoning, customer phone numbers or whole personalized prompts in ordinary logs. Privileged prompt snapshots need explicit access control and existing retention rules.
- Distinguish missing usage from zero, recovered error from unresolved failure, and technical close from caller opt-out.
- Post-call summaries rely on transcripts plus successful tools and server outcomes. “Certainly, tell me” cannot become proof that wedding cards are offered. Tag unresolved requests and proposed follow-up honestly; do not infer a tool succeeded from speech.
- Preview and admin diagnostics consume the actual renderer. Tenant screens show generalized network/integration labels and no wholesale vendor names or internal account/connection identifiers.
- If agent-creation or diagnostic UI changes are implemented, include loading/error/retry behavior and verify those flows with Reticle on the running app. A backend-only change does not require an unrelated UI verdict.

Acceptance: a reviewer can trace why a call ended without guessing; historical transport cleanup cannot misclassify the cause; failure cases do not create false success summaries; tenant-facing responses remain scrubbed.

Files: existing prompt-preview, PSTN diagnostics, failure-log, call ledger and post-call pipeline modules; existing admin/agent-creation surfaces only where necessary.

## 13. Work package J — safely handle already-published agents

**Priority:** required before broad activation. **Depends on:** C–G.

Implementation:

- Inventory published brains and generate a read-only compatibility report: language contradictions, duplicated platform blocks, unsupported tool promises, obsolete close instructions and missing provenance.
- Separate deterministic platform normalization from business regeneration. Preserve old immutable snapshots and original source; create a new reviewed version when semantic business text must change.
- Do not regenerate a customer's script automatically on startup, overwrite a draft, silently change prices or discard exact wording. If the old artifact is ambiguous, require business review before activating its replacement; keep the agent visibly non-callable for a new conflicting version rather than making an answered call fail.
- Apply platform compatibility rendering only where rule ownership is provable and the change is versioned/auditable. Existing active/prewarmed sessions keep their pinned compatible version until completion.
- Roll back by selecting an earlier compatible published artifact plus its platform-policy version for future calls. Do not roll back to an unsafe live route merely to make the error disappear.
- Reuse persisted tier assignments, telephony snapshots and tool authorization. Never use migration/startup to reset these.

Acceptance: dry-run before activation; before/after checksums and coverage report for each changed agent; no unapproved business fact change; no active-call mutation; rollback restores a known compatible version without data deletion.

This work does not authorize destructive migrations, public API changes, production configuration changes, billing-rate changes or publication to production. Those require the existing separate checkpoint with a concrete reviewed change when implementation is requested.

## 14. Verification and release gates

### Test dimensions

- All 12 configured locales, then the enabled subset for each actual STT/LLM/voice combination. New locales must supply speech rules, semantic cases and compatibility checks before becoming callable.
- Composed and native audio contracts; PSTN and browser paths; inbound/outbound; both carrier adapters; campaign personalization; permitted voicemail/callback modes.
- Required critical cases across every eligible locale/pipeline. Use pairwise sampling for lower-risk combinatorial settings, but never omit tenant isolation, wrong-close negatives, exactly-once actions or the primary opening invariant to save test count.
- Native script, code-mixing, transliteration, Unicode normalization, missing punctuation, short requests, negated refusals, product substitution and corrections.
- Success, tool denial, provider length stop, partial output, malformed JSON, 429/5xx, timeout, missing usage, tool write succeeded but reply failed, cancellation, duplicate tools/finals, fast answer, stale prepared session and caller speech during farewell.

### Mandatory release criteria

1. Zero wrong close authorizations across the deterministic multilingual critical corpus, including adversarial wrong model proposals. This is a test gate, not a claim of zero real-world errors forever.
2. Zero lost or duplicated tool side effects and zero false booking/order confirmations in injected failure tests.
3. The two archived call scenarios produce a relevant answer or clarification and remain connected until a real end or categorized exhausted technical failure.
4. Every shipped request branch records and uses a valid effective budget; one bounded recovery allowance; no silent model substitution.
5. Exactly one selected locale pack and effective rule set; exact runtime/preview render parity; mandatory fact/disclosure coverage preserved.
6. Call/agent/tenant snapshot isolation, publication-during-call stability, startup persistence and fast-answer prepared-session ownership pass.
7. Exactly one opening, one authorized farewell and one disconnect. Substantive pre-commit resumption revokes close.
8. Suggested initial latency target: p95 STT-final → first emitted reply audio at or below two seconds for healthy no-tool turns on the evaluated profile. This is proposed, not measured. Report coalescing and carrier delay separately; renegotiate only from observed provider/transport data, not by deleting checks. No silent multi-second recovery without a bounded, appropriate response path.
9. All affected existing suites pass with the three baseline model-selection failures explicitly resolved through the documented contract. No weakened intent assertions.
10. Security check before commit/push: `python scripts/security_audit.py --mode sast`, with zero blocking findings. Preserve tenant filtering/auth/signature rules. Staging DAST follows the project's pipeline when the reviewed environment is available.

### End-to-end evidence

Start with mocked provider/HTTP and real server control-flow tests, then replay stored turn events and recorded audio where available. Validate semantic expectations in each locale with native-language review; a translated corpus or LLM grader alone is insufficient. Use the exact provider/model/API mode selected by the profile in an authorized staging test. No customer calls are needed for initial regression work.

For native audio, verify setup versus per-turn events, interrupted generations, tool response IDs and carrier playback separately. Do not equate model turn completion with the physical line having played the farewell.

Roll out in this order: internal regression harness → non-customer staging calls → internal test agents → limited compatible agent cohort → gradual expansion. Track false-close reports, incomplete-turn rate, recovery success, unresolved needs at close, duplicate action/farewell count and latency percentiles by locale/profile. Stop expansion on any critical regression; rollback applies to new sessions while in-flight pinned sessions drain.

## 15. Delivery order and reviewable changes

Each item is a separate reviewable change with a failing regression, minimal implementation, affected checks and an integration demonstration. No implementation is authorized by the existence of this plan.

1. **A/B:** reproduce both calls; fix the shared initial-tool budget/retry path and honest exhausted-error handling. This immediate repair does not wait for the compiler redesign.
2. **C/D contracts:** extend the existing source-backed AgentSpec and define policy ownership; strengthen extraction/generation/publication.
3. **D/E:** deterministic rule assembly, contradiction validation, session manifest and preview/runtime parity. Integrate existing prewarm and campaign personalization.
4. **F/G:** multilingual interpretation, pending-request tracking, shared close authorization and reversible disconnect, including native tool normalization.
5. **H/I:** turn-taking integration and diagnostics/summary truthfulness, preserving existing opening and safety invariants.
6. **J:** compatibility inventory, reviewed new publications, staging evidence, limited rollout and rollback proof.

Do not make a single large change that simultaneously rewrites the compiler, alters voice profiles and retunes VAD. Separating these changes lets each observed improvement be attributed and rolled back safely.

## 16. Recheck evidence and external technical basis

### Executed during this planning turn

- Read the current generation/creation/publication, prompt assembly, prewarm/admission, close and provider contracts through Graft and exact source spans.
- Confirmed all 12 configured locales have spoken packs.
- Executed the existing prompt validator against the archived contradictory brain: returned `[]` despite the embedded en-IN instruction.
- Executed the remaining-request guard: `why=False`, `ధర=False`, `ఎంత=False`, `price=True`.
- Ran, with live DB/test modes disabled:

```text
.venv/Scripts/python.exe -m pytest server/tests/test_employee_script_pipeline.py server/tests/test_generation_boundaries.py server/tests/test_runtime_prompt_contract.py server/tests/test_primary_script_flow.py server/tests/test_composed_session_repair.py -q --tb=short
222 passed, 3 failed, 2 warnings in 6.73s
```

The three failures are parameterizations of `test_explicit_gemini_stack_never_becomes_secondary` for `None`, empty and invalid model values. No tests were changed. This result is a baseline failure, not a green implementation verdict. The prior audit's separate 65 passing checks are earlier evidence and were not rerun or added to this turn's pass total.

### Official provider guidance checked on 25 October 2026

- Sarvam V1 defines output-token and reasoning parameters and permits explicitly disabling reasoning. The plan tests the serialized selected-model request rather than relying on an undocumented default. [Sarvam Chat Completion V1](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1)
- Google's structured-output guidance requires application-level validation, including handling schema-compliant but semantically wrong values. This supports validating close meaning beyond JSON shape or literal evidence matching. [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- Gemini Live setup carries system instructions and tools; its native setup does not support the ordinary response JSON-schema fields. Its documented generation, interruption, transcription and turn-completion events are distinct. This supports one policy with transport-specific adapters and explicit playback handling. [Gemini Live API reference](https://ai.google.dev/api/live)

These sources support engineering decisions; they do not certify the application as meeting a universal voice-agent standard. Real reliability must be demonstrated by the gates above.

Reticle was skipped for this planning turn because no application UI was changed. Future UI implementation must produce a real flow verdict. Production behavior, arbitrary caller phrasing and all language/voice combinations have not been verified by this plan.
