# Flow matrix 2026-10-30 — scripts x languages x flows

Employee (tenant console) pipeline: solar = outbound sales with objections, shop = inbound support with order
status, clinic = inbound appointments. Live Sarvam turn loop, isolated sim schema, server-truth checks plus a
Gemini judge (OpenAI had no credits). `infra:` = Sarvam key ran out of credits mid-run (fallback line spoken).
Baseline = before fixes; After = latest valid run after fixes (run named per row).

| Flow | Script | Lang | Before | After | After run |
|---|---|---|---|---|---|
| abusive | clinic | en-IN | PASS | PASS | flow-matrix-after |
| abusive | clinic | hi-IN | PASS | PASS | flow-matrix-after |
| abusive | clinic | te-IN | PASS | PASS | flow-matrix-after3-te |
| abusive | shop | en-IN | PASS | PASS | flow-matrix-after |
| abusive | shop | hi-IN | PASS | PASS | flow-matrix-after |
| abusive | shop | te-IN | PASS | PASS | flow-matrix-after3-te |
| booking | clinic | en-IN | PASS | PASS | flow-matrix-after |
| booking | clinic | hi-IN | PASS | PASS | flow-matrix-after |
| booking | clinic | ta-IN | - | PASS | flow-matrix-after2 |
| booking | clinic | te-IN | PASS | PASS | flow-matrix-after3-te |
| callback_no_time | shop | en-IN | PASS | PASS | flow-matrix-after3-targeted |
| callback_no_time | shop | hi-IN | PASS | PASS | flow-matrix-after3-targeted |
| callback_no_time | shop | ta-IN | - | PASS | flow-matrix-after3-targeted |
| callback_no_time | shop | te-IN | PASS | PASS | flow-matrix-after3-te |
| callback_no_time | solar | en-IN | PASS | PASS | flow-matrix-after3-targeted |
| callback_no_time | solar | hi-IN | PASS | PASS | flow-matrix-after3-targeted |
| callback_no_time | solar | ta-IN | - | PASS | flow-matrix-after3-targeted |
| callback_no_time | solar | te-IN | PASS | PASS | flow-matrix-after3-te |
| damaged_refund | shop | en-IN | PASS | PASS | flow-matrix-after |
| damaged_refund | shop | hi-IN | PASS | PASS | flow-matrix-after |
| damaged_refund | shop | te-IN | PASS | PASS | flow-matrix-after3-te |
| dnd_regional | solar | en-IN | PASS | PASS | flow-matrix-after |
| dnd_regional | solar | hi-IN | PASS | PASS | flow-matrix-after2 |
| dnd_regional | solar | ta-IN | - | PASS | flow-matrix-after2 |
| dnd_regional | solar | te-IN | PASS | PASS | flow-matrix-after3-te |
| family_objection_callback | solar | en-IN | FAIL: callback_not_saved | PASS | flow-matrix-after3-targeted |
| family_objection_callback | solar | hi-IN | FAIL: judge:asked_or_accepted_callback_time | PASS | flow-matrix-after3-targeted |
| family_objection_callback | solar | ta-IN | - | PASS | flow-matrix-after3-targeted |
| family_objection_callback | solar | te-IN | FAIL: judge:asked_or_accepted_callback_time | PASS | flow-matrix-after3-te |
| hangup_mid_sentence | clinic | en-IN | PASS | PASS | flow-matrix-after |
| hangup_mid_sentence | clinic | hi-IN | PASS | PASS | flow-matrix-after |
| hangup_mid_sentence | clinic | te-IN | PASS | PASS | flow-matrix-after3-te |
| hangup_mid_sentence | shop | en-IN | PASS | PASS | flow-matrix-after |
| hangup_mid_sentence | shop | hi-IN | PASS | PASS | flow-matrix-after |
| hangup_mid_sentence | shop | te-IN | PASS | PASS | flow-matrix-after3-te |
| language_switch | clinic | en-IN | PASS | PASS | flow-matrix-after |
| language_switch | clinic | hi-IN | FAIL: speech:no_native_script | FAIL: speech:no_native_script | flow-matrix-after |
| language_switch | clinic | ta-IN | - | FAIL: speech:no_native_script | flow-matrix-after2 |
| language_switch | clinic | te-IN | FAIL: speech:no_native_script | FAIL: speech:no_native_script | flow-matrix-after3-te |
| objection_twice | solar | en-IN | PASS | PASS | flow-matrix-after4 |
| objection_twice | solar | hi-IN | PASS | PASS | flow-matrix-after4 |
| objection_twice | solar | ta-IN | - | PASS | flow-matrix-after4 |
| objection_twice | solar | te-IN | PASS | PASS | flow-matrix-after4 |
| objective_followthrough | solar | en-IN | FAIL: speech:internal_review_text_spoken | PASS | flow-matrix-after |
| objective_followthrough | solar | hi-IN | PASS | PASS | flow-matrix-after |
| objective_followthrough | solar | te-IN | PASS | PASS | flow-matrix-after3-te |
| order_status | shop | en-IN | FAIL: speech:internal_review_text_spoken, speech:order_id_mangled | PASS | flow-matrix-after |
| order_status | shop | hi-IN | FAIL: speech:order_id_mangled | PASS | flow-matrix-after |
| order_status | shop | ta-IN | - | PASS | flow-matrix-after2 |
| order_status | shop | te-IN | FAIL: speech:order_id_mangled | PASS | flow-matrix-after3-te |
| refuse_no_dnd | solar | en-IN | FAIL: agent_did_not_close | PASS | flow-matrix-after4 |
| refuse_no_dnd | solar | hi-IN | FAIL: agent_did_not_close, disposition:interested | PASS | flow-matrix-after4 |
| refuse_no_dnd | solar | ta-IN | - | FAIL: disposition:new_lead | flow-matrix-after4 |
| refuse_no_dnd | solar | te-IN | FAIL: agent_did_not_close | FAIL: disposition:new_lead | flow-matrix-after4 |
| unclear_audio | clinic | en-IN | PASS | PASS | flow-matrix-after |
| unclear_audio | clinic | hi-IN | PASS | PASS | flow-matrix-after |
| unclear_audio | clinic | te-IN | PASS | PASS | flow-matrix-after3-te |
| unclear_audio | shop | en-IN | FAIL: speech:internal_review_text_spoken, judge:asked_to_repeat_or_offered_help_without_inventing | PASS | flow-matrix-after |
| unclear_audio | shop | hi-IN | PASS | PASS | flow-matrix-after |
| unclear_audio | shop | te-IN | PASS | PASS | flow-matrix-after3-te |

Before: 38/51 passed.
After (valid, non-outage): 55/60 passed (0 outage-only cases excluded).

## Admin compiler path (compile_agent_from_brief), after fixes

| Case | Result |
|---|---|
| en-IN/booking/clinic | PASS |
| en-IN/callback_no_time/shop | PASS |
| en-IN/callback_no_time/solar | PASS |
| en-IN/objection_twice/solar | PASS |
| en-IN/objective_followthrough/solar | PASS |
| en-IN/order_status/shop | PASS |
| en-IN/refuse_no_dnd/solar | PASS |
| te-IN/booking/clinic | PASS |
| te-IN/callback_no_time/shop | PASS |
| te-IN/callback_no_time/solar | PASS |
| te-IN/objection_twice/solar | PASS |
| te-IN/objective_followthrough/solar | PASS |
| te-IN/order_status/shop | PASS |
| te-IN/refuse_no_dnd/solar | FAIL: agent_did_not_close |

## Missed calls (follow-up policy)

| Mode | DND | Jobs | Pass |
|---|---|---|---|
| off | False | [] | True |
| review | False | [['missed', 'needs_review', 'approval_required']] | True |
| automatic | False | [['missed', 'scheduled', 'missed_call']] | True |
| automatic | True | [['missed', 'suppressed', 'do_not_call']] | True |

## Notes

- Baseline lead checks were tenant-wide (weaker); after-fix runs check leads by the case's caller phone.
- `refuse_no_dnd` te-IN/ta-IN `disposition:new_lead`: the call now closes correctly; the post-call summary model
  still labelled it new_lead. Fixed afterwards in `post_call_pipeline.py` (verified refusal close => not_interested,
  unit-tested in `server/tests/test_brain_flow_coherence.py`), not re-simulated.
- `language_switch` hi/te/ta: when the caller explicitly asks for English the agent answers that turn in English, then
  returns to its configured language. The language pack says to stay in the configured language; this is a product
  policy decision, left unchanged.
- Admin compiler te-IN `refuse_no_dnd` ran before the stricter refusal tie-breaker; the employee-pipeline rerun
  (`flow-matrix-after4`) closes in all four languages.
- Earlier after-fix runs (`flow-matrix-after`, `-after2`) include cases where SARVAM_API_KEY ran out of credits
  mid-run; those are tagged `infra:provider_outage_fallback_spoken` and superseded by later runs.
