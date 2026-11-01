# Verification of Telugu adaptive audit fixes — 29 October 2026

**Verdict: partially implemented; critical problems remain. Do not call this fully fixed.**

This is a verification of the current working tree against findings F1–F11 in the original AUDIT.md. Application code was not changed during this verification. New test/evidence files were added. The tests retain failures rather than weakening assertions.

## What was actually rerun

- 53 fresh conversation sessions: 44 live adaptive caller sessions and 9 disclosed fixed probes. 231 caller turns; 912 recorded Sarvam requests (209 caller and 703 subject/control/tool-selection/speech).
- Current Standard stack: medium / 5b3ecb0dcd721b7f; Sarvam sarvam-105b-conversations; Telugu te-IN. No tier, model, billing rate or production configuration was changed.
- Each caller turn runs through the production composed voice loop, current compiled platform sections, actual control classifier, memory update/projection, authorized tool router, action journal, post-call outcomes and lifecycle. The caller reads the actual delivered answer before choosing its next utterance.
- TTS/STT, external integration transport and carrier are mocked. This proves text/runtime behavior and the server's handling of an acknowledged simulated hangup. It does not prove audio naturalness, acoustic interruption behavior, real OAuth, real calendar/CRM writes or live carrier disconnection.
- Fresh creation was attempted through the real analyze/build endpoints. Business A returned HTTP 422 generation_needs_review at extraction, with a draft retained. Evidence is in ../telugu-adaptive-fixes-20261029/agents/A-build.json and runner-output.log. That attempt did not reach calls. Do not count it as successful fresh script generation.
- To verify existing agents, this rerun used the original three published synthetic agents in the owned audit schema, fresh call/session IDs and fresh per-call memory. Platform sections are refreshed by the current runtime. The saved business scripts were not freshly generated after the creation failure. Existing audit leads/jobs can appear in DB evidence; callback/job claims here use the current source call ID, not an unfiltered row count. The four new probes use previously unused synthetic numbers.
- Application source drift during the verification: 0 files. Reticle was skipped because this is a backend/text verification with no UI change.

## Automated test evidence

- Focused call/speech/memory/post-call run: 154 passed (tool-observed result).
- Prompt/language run: 451 passed; prompt-regression-tests.log.
- Memory/callback/scheduler/playback/creation regression run: 175 passed, 6 failed; runtime-regression-tests.log. All six failures are existing strict expected-dictionary assertions that now receive an added modality field. Names are retained in those cases; these six failures are compatibility/test maintenance gaps, not six demonstrated name-loss bugs.
- Independent negative controls: 4 failed, 0 passed; remaining-gaps-tests.log. These reproduce actual remaining behavior: rejected product accepted as selected, different CRM idempotency key after adding optional phone, 40 interest points without buying evidence, and old persistence overwriting new memory under forced concurrency.
- These runs overlap. Their counts must not be added into a unique-test total. Individual suite passes do not mean all live scenarios passed.

## Findings F1–F11

### F1 — Contextual close, callback and DND: NOT SOLVED (critical)

The semantic channel is implemented, but its quote check only proves that words occurred. It does not validate their meaning or scope. In A_memory_probe T2 the caller says they want visiting cards and are only asking about wedding-card prices. The classifier proposes not_interested plus do_not_call using 'Wedding cards ఆర్డర్ చేయడం లేదు.' The native gate accepts it, hangs up, and persists active DND. The caller still wanted information. In C_self_callback_permission_probe the caller explicitly permits future offers and says 'నా number block చేయకండి' (do not block my number); the model uses that same negated quote as DND evidence and the server saves DND.
B_enquiry_success T3 asks for an email confirmation; the classifier calls that callback intent. On the later goodbye, a new callback record is saved and the farewell claims that a callback was requested. This is visible in the current call's DB rows, not an old job.
The added probes show an even simpler failure: 'కాల్ ముగించండి' (end this call) is treated as do_not_call. A_addressing_agent_name, A_rejected_product_memory and C_callback_withdrawn_after_question all persist permanent DND after an ordinary final goodbye. Ending this call does not withdraw future contact permission. A_dnd_question_then_goodbye has the expected final DND, but its first control proposal is null; that final pass does not prove immediate opt-out persistence on a continuing turn.
Source: server/call/semantic_call_control.py:19–35,52–57; server/call/live_turn_orchestrator.py:208–213. The semantic gate returns before the older shared validator and trusts contact_intent plus substring evidence. DND on a continuing turn also needs a durable latch independent of closing; see the added DND probe below.
Required: validate actor, future-contact scope, negation, unanswered requests and action state together; persist genuine opt-out immediately; never treat declining one product or requesting an email as telephone consent. Reuse shared transport/action guards in the native path. Do not solve this by growing Telugu phrase lists.

### F2 — Speech escaped before final guards: FIX VERIFIED within this text path

Native speech deltas are held until the final guarded text. Current sessions no longer show the old pattern of speaking an unsafe draft and then appending its replacement. The farewell-resumption case legitimately includes a farewell already started and the resumed answer in one harness turn; that difference must not be mislabeled as duplicate speech. Real TTS playback was excluded.
delivery-verification.json compares 231 delivered turns with their final guarded text after the current spoken formatter. There is one explained difference in B_farewell_resume and zero unexplained differences. formatter-verification.json retains eight exact currency/clock reproductions, all passing.
Source: server/call/live_turn_orchestrator.py, _stream_composed_speech; server/services/pstn_voice_core.py, done/replace_speech handling. Raw session done events and speech sinks are retained.

### F3 — Memory delivery: HOT PATH FIX VERIFIED; persistence is still unsafe

The rerun measured 159 loads with local facts; 0 lacked a projection. Maximum observed memory-load duration was 0.016s. Real request bodies include [Memory projection]. This fixes the earlier hot-memory timeout loss in this run.
However, the new concurrency test proves an old snapshot can still overwrite newer disk/cache state. The sequence check and write are outside a serialized per-call operation. It can pass the old sequence check, pause, let the new snapshot persist, then overwrite it. Merely checking an incremented counter in a sequential test does not prove write ordering.
Source: server/call/memory_manager.py:244–253. Required: serialize persistence per call or use a version-aware atomic write/CAS, while keeping hot snapshot reads independent of I/O. Track committed/projected/consumed versions.

### F4 — Selected facts, alternatives and caller identity: NOT SOLVED

The negative control 'నాకు మగ్స్ వద్దు, కార్డులు కావాలి' accepts mugs as selected product because any negation makes the entire evidence quote 'corrected'. An addressed agent name can also become caller_name: A_enquiry_none T1 stores Kavitha; B_enquiry_success T4 overwrites the caller with Suresh. C_enquiry_success stores Madhavi. These are actual saved memories from fresh calls.
Source: server/call/memory_guard.py:48–80 and close_classifier memory extraction. Required: clause/target-aware assertion and correction semantics, speaker-role validation for personal fields, and evidence/turn/version per selected slot. Reject the negated value while retaining the positively selected alternative.

### F5 — 120-character history clipping: IMPROVED; full design incomplete

The defaults/configuration are larger and ordinary replies survive; recent test dialogues no longer exhibit the original 120-character split fee. The remaining truncator still cuts by characters/word boundary with a remaining-text marker. That is not a token-budgeted complete-utterance/sentence policy and can still split a multiword numeric fact. Treat the original common failure as improved, not every history edge case as solved.

### F6 — Currency/clock corruption: FIX VERIFIED for the reported reproductions

Currency token boundaries no longer consume the rs suffix of Orders; explicit PM beside Telugu suffixes is preserved; a bare small hour no longer gains an invented AM; Telugu currency and /- cases pass. Existing spoken-number tests and the new audit regressions pass. This does not by itself prove every language's number pronunciation.

### F7 — Tool receipts, action identity and explanation: PARTIAL

Calendar availability can now progress to CREATE_EVENT, and the runtime retains action receipts. Yet C_crm_success gets a created-contact receipt and an enquiry_saved proof while the delivered answer still says the request cannot be confirmed. The independent identity test produces a new CREATE key for the same email when optional phone is supplied later. Unknown calendar results can replace the entire answer with a generic uncertainty sentence, skipping unrelated service questions and repeating the read. C_crm_failure selected no external CRM transport action in this rerun: it cannot count as a live failed-CRM test merely because the scenario name says failure. Calendar unknown-result fixtures did execute. Internal enquiry saving and external CRM/calendar operations must be judged separately.
Source: server/services/tool_router.py:149–165; live_turn_orchestrator tool/speech path. Required: a stable primary identity (email, then fallback), typed action receipts that distinguish enquiry/CRM/event, and a reply that explains failure while answering remaining questions. Avoid speculative success or repeating uncertain writes.

### F8 — Calendar time: INDIA DATE IMPROVED; configuration/regression gaps remain

Live availability/event requests now use 30 October 2026 for tomorrow rather than a 2025 date. But the context defaults to Asia/Kolkata when ctx.timezone is missing; the CallContext has no declared timezone and the only explicit ctx.timezone assignment located by the graph is in the new test. The fix has not demonstrated tenant timezone plumbing. In integration_calendar.py:39–48 the new past-date guard also rejects historical LIST_EVENTS reads, although the audit explicitly required preserving legitimate past-calendar reads. Transport mocking means that real adapter path is covered by source/unit review, not these live tool fixtures.

### F9 — Product facts and unwanted sales pressure: NOT SOLVED

B_enquiry_success applies the fridge-only 250 inspection charge to split AC and includes that condition in the calendar event description. C_diversion_safety says the course fee will not change and there are no hidden charges without supplied evidence. Repeated order/demo prompts and skipped questions remain. A_deep_enquiry eventually says the standard price is unavailable despite the supplied business price.
Required: product-scoped fact retrieval with explicit units/conditions, deterministic approved-price arithmetic, unknown-field handling and question/task state. More prose telling the model to be accurate has not enforced these facts.

### F10 — Consent, outcome tags and scoring: PARTIAL

True DND is canonicalized after model analysis and callback tags are removed in tested final DND outcomes. But false DND from F1 now also canonicalizes an interested caller as not_interested. The scoring change awards interest to every new_lead even with no facts: the independent test observes 40 points. The audit required evidence of buying intent, not a blanket bonus for the label. Genuine new enquiries should receive points from recorded intent/requirements without enabling contact or conversion automatically.

### F11 — One compiled contract with no duplicated rules: NOT COMPLETE

The effective saved-agent prompt remains around 20–21K characters; one selected Telugu pack is present, not all languages. The speech-only prompt still includes JSON-session/spoken_response guidance and overlapping generic action/closing wording. The anti-repeat hint says not to repeat facts even when callers are trying to confirm details. Fresh generation did not complete, so a new compiler output cannot be claimed verified. No token-budget exception in the observed Sarvam requests establishes prompt length as the cause of the semantic failures.

## Additional live negative controls

These fixed probes use live subject inference and production orchestration. They are disclosed fixed stimuli, not an adaptive caller pretending to generate them.

- A_dnd_question_then_goodbye: PASS — {"passed": true, "observed_preference": "do_not_call"}
- A_addressing_agent_name: FAIL — {"passed": false, "facts": {"caller_name": "ఇంకా"}, "no_false_dnd_on_goodbye": false}
- A_rejected_product_memory: FAIL — {"passed": false, "product": "విజిటింగ్ కార్డులు", "selected_product_correct": true, "no_false_dnd_on_goodbye": false}
- C_callback_withdrawn_after_question: FAIL — {"passed": false, "callback_records": 0, "jobs": 0, "preference": "do_not_call"}

## Server hangup result

51 sessions received an agent-initiated acknowledged simulated hangup; 52 carrier attempts and 51 acknowledgements were recorded. 0 sessions had harness exceptions. See case-summary.json for each session. A completed disconnect is not proof that the decision to disconnect was right: the false DND cases demonstrate the opposite.
Sessions that reached the turn limit are not automatically hangup failures. Their final caller turn must actually ask to finish; some adaptive callers continued enquiries until the imposed limit. The carrier-failure fixture deliberately rejects one attempt before recovery. Real carrier/API behavior and greeting/prewarm were not changed or revalidated here.

## Evidence and next work

- TRANSCRIPTS.md: every caller turn, delivered reply, final text, memory and outcome.
- sessions/: raw control proposals, gate results, carrier timeline, actual action payloads, memory loads and current-call DB evidence.
- batches/main and batches/additional: request bodies, network records, exact scenario plans and result indices. Requests use synthetic audit data; protect them as internal evidence.
- test_remaining_gaps.py / remaining-gaps-tests.log: reproducible remaining failures, deliberately retained red.
- additional-probe-checks.json, verification-stats.json, case-summary.json: machine-readable results.
Fix F1 first because it can end a useful conversation and block an interested caller. Next fix memory semantics and persistence ordering, action identity/result reporting, then business fact scope, timezone plumbing, score evidence and compiled-contract duplication. Rerun these same negative controls after changes. No current evidence supports saying all problems are solved.
