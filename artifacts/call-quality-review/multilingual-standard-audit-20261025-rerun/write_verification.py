"""Write a self-contained verification report from the latest frozen-source run."""
import ast,hashlib,json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
M=json.loads((P/'metrics.json').read_text(encoding='utf-8'));B=json.loads((P/'baseline.json').read_text(encoding='utf-8'))
O=json.loads((P.parent/'multilingual-standard-audit-20261025/metrics.json').read_text(encoding='utf-8'))['overall']
H=json.loads((P/'handshake-results.json').read_text(encoding='utf-8'));A=json.loads((P/'audio-smoke.json').read_text(encoding='utf-8'))
C=json.loads((P/'verification-context.json').read_text(encoding='utf-8'))
def link(path,label=None,repo=False,line=None):
 f=(ROOT if repo else P)/path
 return f'[{label or path}](<{f.as_posix()}{":"+str(line) if line else ""}>)'
def symbol(file,name):
 tree=ast.parse((ROOT/file).read_text(encoding='utf-8'))
 node=next(n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==name)
 return link(file,file+':'+str(node.lineno),True,node.lineno)
def test_summary(file):
 s=(P/file).read_text(encoding='utf-8-sig');hits=re.findall(r'\d+ passed[^\n]*',s)
 return hits[-1] if hits else 'No passing summary recorded; inspect log.'
def count(name):return M['overall'][name]
main={k:v for k,v in M['by_scenario'].items() if not k.startswith(('7_','8_'))}
base_sessions=sum(v['sessions'] for v in main.values())
failure_sessions=sum(v['sessions'] for k,v in M['by_scenario'].items() if k.startswith(('7_','8_')))
before=json.loads((P/'baseline.json').read_text(encoding='utf-8'))['source_hashes']
frozen=json.loads((P/'frozen-source.json').read_text(encoding='utf-8'))
changed=[f for f,h in frozen.items() if before.get(f)!=h]
drift=[f for f,h in frozen.items() if not (ROOT/f).exists() or hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=h]
o=M['overall']
blocking=bool(o['harness_errors'] or o['early_closes'] or o['missed_explicit_ends'] or o['technical_farewells'] or o['generic_continuations'] or o['empty_responses'] or o['raw_control_speech'] or o['duplicate_hangups'] or o['hangup_during_playback'] or o['unproven_spoken_claim_flags'] or o['unavailable_promise_flags'] or M['request_budget_checks']['failed_write_promise_flags'] or M['request_budget_checks']['missing_unavailable_request_boundary'] or M['request_budget_checks']['non_request_warning_replies'] or M['request_budget_checks']['saved_reference_not_delivered'] or drift)
blocking=blocking or any(not x['pass'] for x in H) or any(x['status']!='passed' for x in A)
complete=base_sessions==270 and failure_sessions==30 and len(H)==20 and len(A)==5
verdict='PASS for the recorded scope' if complete and not blocking else 'INCOMPLETE/FAIL — inspect measurements'
date=datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime('%Y-%m-%d %H:%M IST')
language_lines=[]
for lang,m in M['by_language'].items():language_lines.append(f'- **{lang}:** {m["sessions"]} sessions; {m["reached_turns"]}/{m["planned_turns"]} planned turns reached; {m["technical_farewells"]} technical farewells; {len(m["early_closes"])} premature closes; {len(m["missed_explicit_ends"])} missed explicit endings; {m["integration_attempts"]} mock action attempts, including failure probes.')
scenario_lines=[f'- **{name}:** {m["sessions"]} sessions, {m["reached_turns"]}/{m["planned_turns"]} reached turns; {m["technical_farewells"]} technical farewells, {len(m["early_closes"])} premature closes, {len(m["missed_explicit_ends"])} missed endings.' for name,m in M['by_scenario'].items()]
text=f'''# Standard-tier fixes and fresh multilingual verification

Generated {date}. **Verdict: {verdict}.** This verdict covers the recorded synthetic scenarios and checks below. It is not certification of arbitrary conversations, production deployment, native-speaker naturalness, or a physical carrier disconnect.

## Outcome

The original audit showed response-format failures, useful answers discarded by a rejected close, false callback closes, missed native-language endings and integration failures. The current working tree already contained many attempted fixes when this task began. I preserved that work, added fixes for the remaining failures reproduced here, and used three new business briefs rather than relying solely on the original examples.

- **{len(M['builds']['ready'])} ready agent/locale variants** from three new business identities and five eligible languages.
- **{base_sessions}/270 main sessions** and **{failure_sessions}/30 additional integration-failure sessions** executed with the real selected model. Verification uses the documented impact-based rerun below; these were not all executed on one final source hash.
- **{o['reached_turns']}/{o['planned_turns']} planned caller turns** reached, using **{o['requests']} recorded real Standard LLM requests**. The five full audio smoke sessions and diagnostic contract probes are additional and are not mixed into these counts.
- **{o['technical_farewells']} technical-error farewells**, **{o['generic_continuations']} generic continuation-only replies**, **{len(o['early_closes'])} premature closes**, and **{len(o['missed_explicit_ends'])}/{o['explicit_ends']} missed explicit ending turns** in the final matrix.
- **{o['integration_attempts']} mock integration attempts**, with success, denied-write and unknown-timeout outcomes tested. A recorded attempt is not automatically a successful save; failure cases must be interpreted by their mode.
- **{o['duplicate_hangups']} duplicate hangups**, **{o['hangup_during_playback']} disconnect callbacks during simulated farewell playback**, and **{len(o['unproven_spoken_claim_flags'])} unproven completed-action claims flagged in the final spoken text** by the existing server validator. This lexical check is supplemented by transcript inspection; it is not an independent proof of every possible semantic property.
- **{o['unconfirmed_replacements']} replies consisting entirely of an unconfirmed-action warning**; **{len(M['request_budget_checks']['non_request_warning_replies'])} such warnings on ordinary question turns**. These are reported separately from generic continuation loops and do not count as a verified external save.
- **20/20** deterministic farewell/drain/resume/duplicate/provider-error handshake checks passed.
- **{sum(a['status']=='passed' for a in A)}/5 real audio smoke sessions passed**, using the selected TTS, realtime STT, actual server/model response and selected TTS again.
- Combined regression selection: **{test_summary('all-regression-final.log')}**. Contact-preference tests are included in this total; the earlier separate log is supplementary and is not added again. This is not a full-repository test run.

The main original audit had {O['generic_continuation_turns']}/{O['reached_caller_turns']} generic continuation turns, {O['technical_farewell_turns']} technical farewells, and {O['explicit_end_not_closed']}/{O['explicit_end_turns_reached']} missed explicit endings. Its businesses and reached-turn denominator differ from this new suite, so these are comparative observations, not a controlled statistical success-rate claim.

## Test conditions and boundaries

Current persisted Standard profile was read from the configured development database without changing it: revision **{B['standard']['revision']}**, LLM **{B['standard']['profile']['llm']['modelId']}**, API mode **{B['standard']['profile']['llm']['apiMode']}**, STT **{B['standard']['profile']['stt']['model']}**, selected approved TTS **bulbul:v4-flash**. No model, provider, voice tier or locale fallback was used. Creation used the current configured generation target, separately from the conversational Standard model: `{B['generation_target']}`.

The three new briefs describe **Nila / FreshNest Cleaning**, **Arjun / CityCycle Repairs**, and **Sana / SpeakEasy Language Studio**. They contain exact price/unit conditions, corrected obsolete prices, optional fields, unknown policies, future interest, a changed product need and explicit tool limits. All input contacts are synthetic. Briefs and full generation results are retained in each agent's build JSON. Original audit and previous recheck folders were preserved.

Creation followed the actual website backend's analyze → build → extract/write/review → validation → publication path. The authentication principal was synthetic and agent persistence was isolated, while route permission/tenant parameters and compiler/publication functions ran. The current Standard profile was captured read-only and supplied to the isolated readiness resolver. The matrix substitutes the integration tool loader/router boundary; real gateway authorization and database idempotency are covered by targeted regressions, not by a real external CRM connection here.

Conversation sessions used the actual pinned compiled brain, composer, Sarvam adapter, turn orchestrator, voice loop, close gate and close executor. The large matrix substitutes TTS frames, playback, carrier callback, external CRM capability/result and terminal lifecycle persistence. Each call has a distinct session and call ID.

The full 300-case live matrix was completed, then 135 disconnected cases were rerun after the disconnected-promise guard. Transcript review subsequently caught postposed-negation false positives and promises after failed writes. For that final patch, every non-close saved raw reply was passed through the final deterministic action guards. Exact equality with previously delivered text was required to retain a case; all failed-write probes were selected regardless. **{M['final_source_live_cases']} affected sessions were freshly rerun on the final application source; {M['unaffected_retained_cases']} unaffected sessions retain their actual earlier source signatures and content hashes.** This is impact-based verification, not 300 newly executed final-hash sessions. See {link('guard-impact-review.json','Guard impact review')} and {link('unaffected-case-evidence.json','Retained-case provenance')}. No earlier execution was restamped.

The extra five audio sessions used **real Bulbul v4 Flash audio → real Saaras v3 realtime recognition → actual server/Sarvam LLM → real Bulbul v4 Flash reply audio**. This verifies synthetic speech through the selected stages. It does not reproduce real phone acoustics, human accents, packet loss, echo, interruption timing or SIP/carrier acknowledgments. WAV recordings and recognized text are archived.

Native caller scripts use Telugu, Hindi, Tamil and Kannada script with ordinary English business terms. Some detailed enquiry fields are English, as is common in mixed-language conversations. This is not a native-speaker certification or a monolingual-only benchmark.

The global platform still enables `en-GB`, but Standard revision 91 does not support it. The current language API correctly excludes it from Standard choices and gives a specific unsupported-language error. Three direct creation attempts were rejected before publication. **54 British English combinations remain blocked by actual profile capability**; they were not silently run as Indian English. Fixing this means an explicit supported product configuration, not bypassing the resolver.

## Changes made in this task

### Stable response delivery and the watchdog

Fresh paired probes reproduced **5/10 failures with the full JSON contract** and **3/10 failures with the smaller speech JSON contract**. The same selected model with ordinary native speech completed **20/20 diagnostic requests** across the five supported locales. Those probes are diagnostic samples, not a guarantee of provider reliability.

The composed Sarvam path now uses its native speech transport for conversational answers. Native tool selection stays separate. Speech is buffered until complete, then the existing server validates action claims and closing authorization before TTS receives it. Unexpected JSON/control output is rejected before it can be spoken; there is one bounded recovery with an explicit corrective instruction. Offline structured generation remains available and unchanged in purpose. Source: {symbol('server/call/live_turn_orchestrator.py','_stream_composed_speech')}; {symbol('server/providers/sarvam_llm.py','_stream')}.

The live rerun also exposed a two-request timing bug: selection had completed, but the voice watchdog could still cancel the final speech request as though no progress had occurred. The orchestrator now emits `reply_buffered` after completed selection, preventing that duplicate re-ask while the next request is being validated. Provider transport timeouts still bound failed requests. Source: {symbol('server/call/live_turn_orchestrator.py','_composed_tool_turn')}.

The action/speech/close guard remains active even when optional working-memory extraction is disabled. I also fixed a missing `server_farewell_for` import that could raise `NameError` when an approved close needed its default farewell. Each failure has a regression test that failed before its fix.

These are **Confirmed** findings: paired real-provider probes, captured server failures or failing regressions reproduced the behaviors. General language naturalness and untested production conditions remain unverified; they are not labeled confirmed defects.

### Actual tool availability and capability permissions

The new briefs exposed an overbroad capability rule: the phrase **“No need for delivery address”** enabled order confirmation for a Hindi course agent because the presence of “delivery address” itself counted as order-taking evidence. Address words alone no longer grant the permission, and **“Do not take orders”** is recognized as a prohibition. All final fresh enquiry-only brains deny order confirmation. The affected Hindi course variant was rebuilt through the actual creation flow. Source: {symbol('server/brain/capabilities.py','order_confirmation_evidence')}.

Disconnected agents also sometimes promised an external submission even without a completion claim. Speech generation now receives the actual available action set: when no external tool is connected it explicitly explains that external saving, email or team handoff cannot be promised. Connected cases still require a verified tool result before claiming success. This makes the business script's conditional permission concrete for the session instead of leaving the model to guess whether an integration exists.

Prompt wording alone did not eliminate unsupported future submission promises. The server now replaces those promises in disconnected replies, retaining separate factual sentences and explaining the limitation in the selected locale. Failed or uncertain tool outcomes carry a server-owned flag: the server supplies the unconfirmed-outcome message and retains only separate price statements that pass the narrow factual filter. Other free-form model sentences on that failed-action reply are dropped, including callback promises and retry suggestions. The next caller question can continue normally. This favors an accurate action outcome over paraphrase variety; it does not drop ordinary question replies when no tool failed. A connected agent may still offer an available action before attempting it. The raw model can still propose an invalid action; delivered speech is the guarded output. Source: {symbol('server/call/action_proof.py','replace_unavailable_action_promises')}.

Explicit enquiry-submission requests with no connected gateway also get a deterministic capability answer, even when the model only quotes a price and overlooks the submission request. High-confidence request detection adds a limitation and never grants action permission. Negated “do not save” instructions preserve the ordinary question flow. The native/mixed-script positive and negative examples in all five locales are covered by regressions. No confirmed mock save reference is suppressed in the final evidence.

Manual transcript inspection found **19 original final-matrix warning-only replies** caused by the existing validator misreading English contractions and postposed Indic negation, such as “confirmed booking இல்ல” and “confirmed visit ಅಲ್ಲ.” This discarded correct prices or even a successful enquiry reference. Negation now stays local to the relevant clause and handles the observed native/mixed forms; an unrelated “no refund” still cannot authorize a confirmation. The guard also removes every unsupported recorded-request sentence instead of only the first one. Red/green regressions and fresh affected sessions cover these findings. Source: {symbol('server/call/action_proof.py','_claim_is_negated')}. The locale patterns are bounded safeguards, not universal semantic understanding of every possible language phrase.

### Generation validation and active facts

One initial Kannada cleaning build was correctly rejected because the generation/review model returned a Bengali opening. The compiler now permits one grounded repair with the deterministic locale-validation finding, then reruns all normal validation. It never publishes an incompatible opening just because the generative reviewer said “passed.” Persistent invalid output still fails closed. Source: {symbol('server/brain/employee_script_pipeline.py','compile_employee_script')}.

The new “old kitchen note” wording also exposed a gap in active-price normalization. The canonicalizer now handles named-service qualifiers between “old” and “note/price/fee,” retaining the corrected active value and dropping orphaned “discard it” text. Affected cleaning variants were regenerated. Source: {symbol('server/brain/fact_canon.py','canonicalize_superseded_facts')}.

The runtime still maintains per-session history and memory. Each ready brain's language-pack and checksum checks are recorded in metrics. Historical price literals in explicitly conditional objection examples, if present, are distinguished from active offer facts; their presence alone is not counted as a wrong quoted price.

**Memory boundary/tradeoff:** runtime working memory was `{C['working_memory_enabled']}`, call archive `{C['enable_call_archive']}`, optional separate extraction fallback `{C['memory_extraction_fallback']}`, and rolling-summary interval `{C['rolling_summary_interval_turns']}`. Native speech does not emit model-authored JSON `memory_update` proposals. The server still derives caller-detail/correction operations and maintains bounded history/rolling summaries. This short-call suite does not establish parity for arbitrary long-call goals/preferences formerly expected from structured model proposals; that needs a separate long-call memory evaluation. No silent alternate-model memory extractor was enabled.

## F01–F10 disposition

- **F01 — response contract:** further fixed here; final native response path, raw-control rejection, bounded recovery, frozen-source live rerun and real audio smoke provide evidence. Provider outages or rate limits remain external failure possibilities.
- **F02 — answer/safety refusal lost on rejected close:** the existing answer-preserving fix was retained; additional action-negation false positives found here were fixed. Fresh factual, alternate-product, diversion and dangerous-question cases exercise it. No generic continuation loops occurred in the final matrix. Harmful instructions were not observed in reviewed refusal responses; broad safety red-team certification is outside this corpus.
- **F03 — false callback from negation/future interest:** existing shared intent/callback fixes retained and retested with the exact negative callback meaning in native/mixed scripts. Future interest is not treated as permanent DNC.
- **F04 — missed native ending/opt-out:** existing intent/gate-precedence fixes retained. Explicit end, rejection and opt-out cases are counted separately from provider-error exits. Durable production suppression-list writes are not claimed from this isolated matrix.
- **F05 — caller resumption during farewell:** existing revocable-close fix retained; all five locales pass the deterministic caller-resumption check alongside drain, duplicate and provider-error checks. Actual acoustic barge-in remains a separate test boundary.
- **F06 — tools not executed / wrong success type:** native selection and typed proofs retained; actual availability context, unsupported future promises and failed-outcome delivery were strengthened here. Success, denied and unknown-timeout replies use the actual server tool orchestration with a synthetic gateway. There is no real external CRM write.
- **F07 — contradictory instructions/active facts:** existing platform-owned farewell and sentence-completion fixes retained; active-price qualifier normalization improved here. Language-pack count, obsolete-value flags, script and runtime prompts are archived for inspection.
- **F08 — British English mismatch:** the readiness/API fix rejects unsupported Standard selection and exposes compatible choices. British English itself remains unavailable on this actual Standard profile; no unsupported configuration was enabled.
- **F09 — generation recovery:** existing bounded transient retries, stage diagnostics and draft/idempotency protections retained. The run observed a generation read timeout recovering through that path. Wrong-locale review output now gets one bounded validated repair. This does not prove unlimited quota or recovery from every infrastructure outage.
- **F10 — translation-dependent capabilities:** the fresh course case found an additional false positive; fixed here with negative/address regression cases. Final enquiry-only variants deny order capability. This corpus does not prove every possible authored permission phrase in every future language.

## Coverage and evidence

### Per language

{chr(10).join(language_lines)}

### Per scenario

The main nine variants cover interested enquiry, future interest, complete rejection, mild abuse plus a real question, threat plus explicit ending, harmless diversion, dangerous request, return to business, bare acknowledgment, explicit goodbye, direct enquiry submission and direct opt-out. The two additional variants test integration timeout/unknown and denied writes.

{chr(10).join(scenario_lines)}

### Test and tooling results

- {link('all-regression-final.log','Combined regression log')}.
- {link('contact-tests.log','Contact preference and opt-out regression log')}.
- {link('handshake-results.json','20 close-handshake traces')}.
- {link('audio-smoke.json','Five real audio-stage traces')}; {link('audio/en-IN-reply.wav','English reply audio')}; {link('audio/te-IN-reply.wav','Telugu reply audio')}; {link('audio/hi-IN-reply.wav','Hindi reply audio')}; {link('audio/ta-IN-reply.wav','Tamil reply audio')}; {link('audio/kn-IN-reply.wav','Kannada reply audio')}.
- Ruff is **not fully clean**: tracked-file comparison found 22 initial findings and 20 remaining, with no introduced finding in that comparison; the removed issues include the undefined farewell function and an unused import. Pre-existing untracked helper files also retain regex-alias style findings. The final comparison/logs should be consulted rather than interpreting tests as a lint pass. {link('lint-comparison.json')}.
- SAST was attempted with the prescribed runner, but **Windows Application Control blocked the Semgrep executable** (`WinError 4551`). It did not complete, and no bypass was attempted. {link('sast.log')}. Mypy is not installed, so static type checking is not claimed.
- Reticle/browser verification was skipped for this task because the edits are backend/model/compiler changes. Existing frontend changes in the initial dirty tree were preserved; their browser behavior was not independently driven in this task.
- One coding agent was used, as requested. Graft supplied source locations before inspection; Chisle guided scoped edits. Graft reported about 271,000 estimated source tokens avoided in the final verification pass (an overlapping-query tool estimate, not a performance benchmark).

The initial working tree was already dirty and HEAD remained `{B['head']}`. The following files changed relative to this task's initial source hashes; no commit, deployment, billing/configuration change or customer call was performed:

{chr(10).join('- '+link(f,f,True) for f in changed)}

Frozen-source drift at report generation: **{len(drift)} files**. Raw sessions carry their actual executed application-source signature; earlier unaffected executions remain explicitly identified. Archived exploratory attempts and superseded affected runs are excluded. The preliminary burst probe included one provider 429, and early paced probes exposed the two-stage watchdog problem; both are retained rather than overwritten as though they never happened.

Request-budget measurements: observed prompt-token peak **{M['request_budget_checks']['observed_prompt_token_peak']}**, output-token peak **{M['request_budget_checks']['observed_output_token_peak']}**, recorded requested output limits **{M['request_budget_checks']['requested_output_limits']}**. Finish reasons and any provider cancellations are retained in metrics. The fix changes the model's delivery contract and server validation; these samples do not establish production capacity or justify raising budgets without measurement.

The selected evidence contains one incomplete model attempt and one cancelled first-reply attempt, followed by successful bounded recovery. They are included in the request totals and raw traces; zero final technical farewells does not mean every provider attempt succeeded. No output-length finish was recorded in this selected matrix.

Mock action accounting: **{M['request_budget_checks']['successful_mock_writes']} successful enquiries**, **{M['request_budget_checks']['failed_mock_write_probes']} denied/uncertain probes**, **{len(M['request_budget_checks']['saved_reference_not_delivered'])} successful mock enquiry references missing from final speech**, and **{len(M['request_budget_checks']['failed_write_promise_flags'])} failed-write future-promise flags**. These counts use known synthetic outcomes, not the model's assertions; promise detection still uses the same bounded lexical guard and is not an independent semantic oracle.

### Artifacts

- {link('metrics.json','Final metrics, exact flags and checksum/language checks')}.
- {link('baseline.json','Read-only profile/configuration capture')}, {link('frozen-source.json','Final source hashes')}, {link('language-contract.json','Actual compatible language API response')}.
- {link('contract-probe.json','Full/reduced JSON comparison')}, {link('plain-probe.json','Native-speech diagnostic comparison')}.
- {link('transcripts-en-IN.md','All Indian English transcripts')}, {link('transcripts-te-IN.md','All Telugu transcripts')}, {link('transcripts-hi-IN.md','All Hindi transcripts')}, {link('transcripts-ta-IN.md','All Tamil transcripts')}, {link('transcripts-kn-IN.md','All Kannada transcripts')}.
- Per-agent `agents/<business>-<locale>/build.json`, `business-script.txt`, `compiled-brain.txt` and `runtime-prompt.txt` preserve the actual website-flow outputs and pinned prompt. Per-case `sessions/*.json` contain actual model outputs, requests, mock tool attempts, speech passed to TTS and close-gate evidence.
- {link('run_fresh.py','Reproduction harness')}, {link('finish_runs.py','Sequential matrix runner')}, {link('audio_smoke.py','Real synthetic-audio runner')}, {link('analyze_fresh.py','Measurement script')}.

## Limits of this verdict

The final corpus demonstrates the previously failing intent, answer-delivery, action and close behaviors under the stated conditions. The measured improvement is substantial; it does not justify “works perfectly without any issues.” Real PSTN/SIP disconnect acknowledgment and prepared-opening handoff, customer database durability, production load/capacity, human accents and background noise, long calls beyond this corpus, native-speaker quality review, all safety categories, production rollout and the blocked SAST scan remain outside the passing claim. Exact prices, language fluency and conversational relevance should still receive a native-speaker sample review; deterministic guard checks are not an independent semantic grader. Standard British English is explicitly blocked by the current profile.

VERDICT: {verdict}.
'''
(P/'VERIFICATION.md').write_text(text,encoding='utf-8')
(P/'completion.json').write_text(json.dumps({'verdict':verdict,'complete_matrix':complete,'base_sessions':base_sessions,'failure_sessions':failure_sessions,'source_drift':drift,'changed_files':changed,'metrics':M['overall']},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'verdict':verdict,'sessions':o['sessions'],'base_sessions':base_sessions,'failure_sessions':failure_sessions,'words':len(text.split()),'source_drift':drift}))
