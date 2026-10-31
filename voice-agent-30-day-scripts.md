# 30 days of building a PSTN voice agent in public

Prepared from a static review of [MOHAN8897/voice-agent](https://github.com/MOHAN8897/voice-agent), commit `4956d211a1e7d36cf39953a1a53e77774f80a031` (2 September 2026). Reviewed on 22 October 2026.

These are first-person, ready-to-record scripts for approximately 45–65-second videos, depending on delivery and demonstrations. The opening sentence is the hook; the closing sentence is the audience invitation. Visual directions and evidence notes are production notes, not spoken lines.

The series tells the story from foundations through production hurdles. It does not claim the existing repository was written on these future posting dates. Record planned improvements as work in progress until you have demonstrated them. Property qualification is the running example because the code includes budget/location/timeline qualification and site-visit outcomes; it is not evidence of an existing property customer.

“From scratch” here means building the website, backend, orchestration, memory, and telephony integration using existing speech and language models. It does not mean training STT, TTS, or an LLM from scratch.

## What I actually found in the repository

| Area | Evidence-backed position |
| --- | --- |
| Website | Next.js 14, React, TypeScript, marketing pages, a business console, a developer portal, agent workspaces, Test Studio, call investigation, and analytics components. The older `client/` implementation also remains. |
| Backend | FastAPI with provider adapters, configuration resolution, agent brains, lifecycle services, call persistence, memory, and post-call outcomes. |
| Providers | Sarvam STT/TTS and OpenAI LLM adapters; DeepSeek and experimental Cartesia implementations are conditional on configuration. Gemini is represented by a stub catalog entry, not an available LLM adapter. |
| Telephone transport | Current code uses Exotel AgentStream. Several older architecture/PRD documents and database column names still refer to Plivo. |
| Browser streaming | `TurnTtsPipeline` forwards LLM deltas through a text chunker to WebSocket TTS and ordered PCM playback. Short replies may intentionally wait until the chunker flushes. |
| PSTN latency gap | `_run_turn()` collects the full LLM answer before `_speak()`; `_speak()` collects the TTS audio into `pcm_buf` before sending it to Exotel. This prevents equivalent incremental delivery on this path. No live latency was measured in this review. |
| PSTN interruption gap | `_barge_in()` sends Exotel `clear`, but does not cancel the LLM/TTS task. Finals arriving while `_turn_busy` is true are not scheduled by the reader. |
| Lead intelligence | The outcome schema includes dispositions such as `new_lead`, `qualified`, `callback_required`, and `site_visit_planned`, with extracted fields and bilingual summaries. This is not evidence of a complete CRM lead lifecycle or an executed booking. |
| Campaigns | Database entities, management APIs, contact import, and a Redis queue scaffold exist. The worker's `process_job()` logs the job and contains a comment where actual outbound dialing would go. |
| Post-call reliability | Current post-call processing uses an in-process `asyncio.Queue`. The separate worker entrypoint runs the campaign scaffold; it does not provide a durable post-call consumer. |
| CRM and tools | Agent Tools pages explicitly label CRM/webhook configuration as post-MVP. Stored settings are not proof of delivery to a CRM. |
| Benchmarks | Starting a benchmark session marks it completed and creates result skeletons with `None` metrics and `pending_runner` status. The implementation explicitly says automated execution is not wired. |
| Metrics | The live-turn trace currently sets `tts_first_audio_ms` to `None` and `e2e_ms` to brain latency. Those fields do not establish actual caller-perceived end-to-end latency. |
| Product trust | The default behavior prompt says to avoid saying it is AI unless asked. An upfront automated-assistant introduction is a proposed product change, not current default behavior. |
| Production access | Auth and RBAC foundations exist, but some campaign operations fetch by campaign ID without tenant scoping. The Exotel WebSocket accepts paths that do not require a valid stream token. These are hardening tasks, not proof that all routes are secure. |

This was source inspection, not a live deployment audit. No real calls were placed, no paid providers were invoked, and the test suite was not run. Existing test files and CI workflows were inspected; their presence is not a current passing result.

## How the platform works

The website is the control surface: a business configures its agent, business information, voice, and calling settings, then reviews calls and outcomes. FastAPI owns the runtime and persistence.

The intended phone conversation loop is:

```text
Inbound caller, or outbound call request
    → Exotel connects the telephone call over PSTN
    → Exotel opens a bidirectional audio WebSocket to FastAPI
    → STT turns caller audio into text
    → LLM uses the locked business brain + recent turns + compact call memory
    → TTS turns the reply into audio
    → Exotel plays the audio to the caller
    → repeat until hang-up
    → finalize transcript, recording, and memory
    → post-call model produces structured outcome and follow-up information
    → future CRM connector delivers an actionable record
```

PSTN means the public telephone network. WebSockets carry audio between Exotel and your backend; they do not replace the telephone network. STT listens, the LLM chooses the reply, TTS speaks, VAD helps detect speech boundaries, and the orchestrator coordinates state and timing.

The browser path and telephone path share core services but currently differ in streaming and cancellation behavior. Campaign dialing and CRM delivery still have the implementation gaps described above.

## The scripts

### Day 1 — The customer who called while you were busy

**Script**

“Imagine spending money to get a customer enquiry, then losing the conversation because nobody could answer at that moment.

That is the problem I want to build around.

I’m building a voice-calling platform from scratch: a website where a business configures an AI agent that can speak with people over a regular phone call, understand what they need, and capture information for follow-up.

The difficult part is making the whole journey useful. A pleasant conversation means very little if the customer’s requirements disappear afterward.

Over the next 30 days, I’ll show the architecture, the unfinished parts, and the problems I find along the way.

Where does follow-up break in your business?”

**Show:** An illustrative missed enquiry → conversation → structured follow-up diagram. Label the example as illustrative.

**Code connection:** Call lifecycle, memory, and the post-call outcome schema support this direction. Missed-call impact is the product hypothesis, not a measured customer result.

### Day 2 — Why the website has so many moving parts

**Script**

“A talking demo is one screen. A business actually using it needs much more.

Day two of building my voice-agent platform: the website architecture.

The Next.js frontend contains agent setup, business instructions, voice settings, a testing studio, call history, and analytics. The FastAPI backend runs the conversation and stores the results.

That separation lets me change the website without moving real-time audio processing into a browser page.

My challenge is making all these screens reflect what the backend can really do. A button saying ‘connected’ should correspond to a verified connection. A screen saying ‘completed’ should represent completed work.

Which screen would you open first: agent setup, testing, or call results?”

**Show:** A source-backed tour of marketing, `/app`, and `/dev` routes. Use only rendered screens you can actually demonstrate.

**Code connection:** `web/app/`, `web/components/test-studio/`, and `server/app.py`; screen presence does not establish every feature is complete.

### Day 3 — How an AI reaches a regular phone

**Script**

“How does an AI on a server talk to someone who only has a phone number?

Day three: the telephone connection.

PSTN is the public telephone network. My current integration uses Exotel to connect that network to my backend.

During the call, Exotel sends small pieces of audio over a WebSocket. My backend processes that audio and sends the agent’s voice back over the same connection.

The website controls the setup; the telephone provider carries the call.

The hurdle is coordinating credentials, public callback URLs, stream events, and audio formats. A working microphone demo does not verify those pieces.

Tomorrow I’m following the caller’s audio into speech recognition.”

**Show:** Phone ↔ Exotel ↔ FastAPI diagram, then the Exotel status and Test Studio source/screens.

**Code connection:** `server/routes/dev_exotel.py`, `server/routes/exotel_ws.py`, and `server/services/exotel_pstn_bridge.py`. Manual outbound test code exists; no live call was verified here.

### Day 4 — One wrong number can ruin a lead

**Script**

“If someone says ‘fifteen lakhs’ and my agent records ‘fifty lakhs,’ a fluent reply will not save that lead.

Day four is speech-to-text: STT.

STT converts the caller’s audio into words. Those words become the input to the language model and eventually the lead record.

That makes transcription a business problem as much as a technical one. Budgets, names, locations, and phone numbers need special attention.

My code has streaming speech adapters, but I still need realistic tests for noisy calls and important details. When something is unclear, I want the agent to confirm it instead of confidently continuing with the wrong value.

Which detail does your team have to repeat most often?”

**Show:** A staged audio/transcript example with an incorrect amount and a confirmation question. Do not imply it was an observed production failure.

**Code connection:** `server/providers/sarvam_stt.py`, `server/services/sarvam_ws.py`, and the unclear-speech instruction in `server/prompts/voice_defaults.py`.

### Day 5 — Customers do not speak in language dropdowns

**Script**

“A customer might say, ‘Budget fifty lakhs, location Hyderabad,’ inside a Telugu sentence.

Day five: mixed-language conversations.

My platform is Telugu-first, and the voice instructions explicitly allow familiar English words inside natural Telugu speech.

The challenge runs through the whole pipeline. Speech recognition must preserve the meaning, the language model must understand it, and the voice must pronounce the reply clearly.

Selecting Telugu in a dropdown cannot prove all three work together. The current telephone bridge also opens recognition with a fixed Telugu language code, so broader switching needs testing.

I want real conversation examples before claiming multilingual quality.

Which language combination would you test first?”

**Show:** A clearly labeled test phrase moving through transcript, response, and synthesized audio.

**Code connection:** `server/prompts/voice_defaults.py`, `server/agent/language_resolver.py`, and `_open_stt()` in the PSTN bridge. Language-switching quality is unverified.

### Day 6 — How does the agent know you finished?

**Script**

“A pause can mean ‘I’m finished.’ It can also mean ‘I’m remembering my budget.’

Day six: deciding when the agent should respond.

Voice activity detection, or VAD, helps identify speech and silence. Then the system uses those signals to decide when to process a turn.

Respond too early and the agent cuts the caller off. Wait too long and the conversation feels stuck.

The repository has voice presets that bundle silence timing, interruption settings, and speaking behavior. The hurdle is finding settings that work for natural pauses, background noise, and short answers.

I need to test those situations together, rather than tuning one slider in isolation.

Would you trade a little speed for fewer interruptions?”

**Show:** A waveform with two pauses: thinking versus finished. Compare preset settings without inventing measured results.

**Code connection:** `VOICE_PIPELINE_PRESETS` in `server/prompts/voice_defaults.py` and the STT WebSocket configuration.

### Day 7 — Fluent answers can still be wrong

**Script**

“The most expensive answer my agent could give is a confident answer about an offer that does not exist.

Day seven: the language model.

The LLM reads the transcript, business information, and conversation context, then chooses what to say next.

For a business calling agent, that reply needs boundaries: approved facts, qualification questions, and clear limits on promises.

My business-brain sections include facts, guardrails, and actions the agent is allowed to discuss. But instructions alone do not prove the model will always stay grounded.

The challenge is testing questions about unknown prices, unavailable properties, and unsupported promises.

What should an agent always pass to a person instead of answering?”

**Show:** A test question about an absent offer, the business facts, and the expected clarification.

**Code connection:** `server/brain/sections.py`, `server/brain/semantic_validation.py`, and `server/call/live_turn_orchestrator.py`.

### Day 8 — Two businesses should not share one giant prompt

**Script**

“A clinic and a property business might use the same voice platform. Their agents should behave very differently.

Day eight: separating platform behavior from business knowledge.

Some instructions belong to the platform: keep replies concise, handle unclear speech, and follow conversation rules. Other information belongs to each business: services, facts, FAQs, and qualification criteria.

My code separates these concerns and compiles them into the agent’s brain.

The hurdle is handling contradictions. If one section says ‘never quote a price’ and another supplies a price, the system needs a clear rule and a way to flag the conflict.

Would your team prefer filling structured sections or editing one long prompt?”

**Show:** Platform behavior and business sections combining into a compiled prompt.

**Code connection:** `server/brain/session_brain_compiler.py`, `server/brain/sections.py`, and the Business Brain editor. Compilation organizes instructions; it does not guarantee factual correctness.

### Day 9 — What if the business changes its offer mid-call?

**Script**

“Imagine the agent starts a call with one set of business instructions, then finishes with another because someone edited the settings.

Day nine: configuration versions.

At call start, my lifecycle service resolves the speech and language-model stack and records the compiled-brain version.

That gives the conversation a consistent configuration and gives me a record to investigate afterward.

The challenge is making every live path honor that locked context. A version recorded in metadata is useful only if the runtime actually uses it.

The repository includes tests around version locking, which is the behavior I want to preserve as the platform grows.

Would you want to see exactly which instructions produced a call result?”

**Show:** Call metadata showing a stack combination and brain version; use a real test record or label a mock.

**Code connection:** `server/call/call_lifecycle_service.py`, `server/call/call_context.py`, and `server/tests/test_call_version_lock.py`. Tests were inspected, not executed in this review.

### Day 10 — A good voice needs good sentences

**Script**

“A natural voice reading a paragraph can still make a terrible phone agent.

Day ten: text-to-speech, or TTS.

TTS converts the language model’s reply into audio. But choosing a pleasant voice only solves part of the experience.

The wording needs to be speakable: short sentences, clear numbers, useful pauses, and one question at a time.

My current defaults push the agent toward brief spoken replies, and the platform has voice presets for delivery. The telephone bridge still sets its own pace value, so I need to align effective settings across paths.

The challenge is preserving clarity while keeping the conversation moving.

What makes an automated voice difficult for you to listen to?”

**Show:** The same example spoken as a long paragraph and as two short conversational sentences.

**Code connection:** `server/prompts/voice_defaults.py`, `server/services/tts_config.py`, and `_speak()` in the PSTN bridge.

### Day 11 — I found a real delay in the telephone path

**Script**

“My code can receive a reply as a stream and still make the caller wait for the whole answer.

Day eleven: a real bottleneck I found.

In the telephone bridge, I collect the language model’s full response before starting speech synthesis. Then I collect the synthesized audio before sending it back to Exotel.

That prevents the stages from overlapping the way I want.

The browser code already has a pipeline for forwarding text chunks into TTS, so the two channels currently behave differently.

My next task is incremental delivery on the telephone path and measuring when the caller actually hears the first word.

Would you like to see that before-and-after comparison when it is measured?”

**Show:** Highlight `_run_turn()` and `pcm_buf`, then draw sequential versus overlapping work. Do not add fabricated seconds saved.

**Code connection:** `server/services/exotel_pstn_bridge.py:173` and `:233`; browser counterpart in `web/lib/voice/turn-tts-pipeline.ts`.

### Day 12 — Speaking every token creates another problem

**Script**

“Sending words earlier can make a voice agent faster. Sending fragments too early can make it sound broken.

Day twelve: text chunking.

The language model produces small pieces of text. TTS works better when it receives useful phrases with enough context to pronounce them naturally.

My browser pipeline has a chunker that looks for sentence boundaries, punctuation, and size limits. It can intentionally hold a short reply until the response finishes.

That is the tradeoff I need to tune: waiting long enough for clear speech while avoiding unnecessary silence.

The next challenge is applying the same discipline to the telephone pipeline.

Which would bother you more: a pause or awkward, fragmented speech?”

**Show:** Deltas accumulating into a complete phrase, then entering TTS. Label the short-reply buffering behavior.

**Code connection:** `web/lib/voice/text-chunker.ts` and `web/lib/voice/turn-tts-pipeline.ts`.

### Day 13 — “Stop talking” must stop the whole pipeline

**Script**

“If the caller says, ‘Wait, that is not my budget,’ my agent needs to stop and listen.

Day thirteen: interruptions, also called barge-in.

The telephone bridge detects some partial transcripts while the agent is speaking and sends Exotel a command to clear queued audio.

But I found an unfinished part: clearing playback does not cancel the current generation task. And a final transcript arriving while the turn is busy is not scheduled for a new turn.

So the caller’s correction could be missed or old work could continue.

The challenge is coordinating cancellation, playback, and the next utterance as one operation.

What phrase would you use to interrupt an agent during testing?”

**Show:** Caller correction → clear audio → cancel old turn → preserve and process new utterance. Mark the last two as work to complete.

**Code connection:** `_stt_reader()` and `_barge_in()` in `server/services/exotel_pstn_bridge.py`.

### Day 14 — The agent can hear its own voice

**Script**

“An agent can accidentally answer itself if its own speech comes back through the microphone.

Day fourteen: echo.

In a browser test, speaker audio can leak into the mic. Speech recognition may turn that into a new transcript, and suddenly the agent thinks the customer said its last sentence.

The browser code includes echo checks that compare incoming text with recent assistant speech, plus a cooldown after playback.

The tricky part is that a real customer might repeat the agent’s words. A filter that blocks everything similar can lose a valid reply.

I need tests with speakers, headphones, repetition, and interruptions.

Would you test a voice agent on speakerphone?”

**Show:** A labeled browser test with the speaker-to-microphone feedback path and a legitimate repeated response.

**Code connection:** `web/lib/echo-guard.ts` and `web/components/live/LiveVoiceSession.tsx`. Browser echo checks do not establish PSTN echo handling.

### Day 15 — Remembering a budget without rereading the whole call

**Script**

“The customer already told the agent their budget. Asking again makes the entire conversation feel unreliable.

Day fifteen: working memory.

The code separates three things: the call ledger, structured memory, and a compact memory view sent into the next model request.

The ledger records conversation turns. Memory holds facts and preferences. The compact view helps the agent use those details without resending everything.

The challenge is deciding what matters and keeping it accurate when the caller changes their mind.

This is memory within a call. It does not yet establish that the agent recognizes a returning customer across separate calls.

What should an agent remember throughout one conversation?”

**Show:** Example transcript → budget/location/timeline slots → compact next-turn context.

**Code connection:** `server/call/call_ledger.py`, `server/call/memory_manager.py`, and `server/call/memory_projection.py`.

### Day 16 — Repeating context has a cost

**Script**

“A ten-minute conversation should not require sending ten minutes of raw transcript every time the customer speaks.

Day sixteen: context and cost.

My design keeps the business brain relatively stable and adds compact memory plus recent turns for each new request.

The code also has cache keys based on brain content or version. Those are intended to make repeated instructions reusable where the configured provider supports it.

The hurdle is keeping useful details while shrinking context. Over-compression can remove a qualification rule or an important customer preference.

I have not measured a production saving here. I need token usage and call-quality evidence together.

Would you want a breakdown of what one completed call actually costs?”

**Show:** Stable instructions, changing memory, and recent turns as separate blocks; show real usage only when available.

**Code connection:** `server/services/prompt_cache_key.py`, `server/agent/instruction_builder.py`, and `server/call/memory_projection.py`. Cache eligibility is configuration/model dependent in the current code.

### Day 17 — A customer correction must reach the lead record

**Script**

“‘Actually, make that sixty lakhs.’ That one sentence needs to change what the agent remembers.

Day seventeen: structured memory updates.

The live-turn design asks the model for a spoken response and proposed memory changes in the same request.

A memory manager validates supported operations and records accepted changes. That lets me inspect how the customer profile evolved during the conversation.

But valid JSON does not guarantee a true fact. A correctly shaped update can still contain the wrong amount or an assumption the caller never confirmed.

The challenge is testing corrections, conflicting details, and uncertainty all the way through to the final outcome.

What correction would expose a weak sales agent?”

**Show:** Initial budget → caller correction → proposed update → validation → updated snapshot.

**Code connection:** `server/call/live_turn_schema.py`, `server/call/live_turn_orchestrator.py`, and `server/call/memory_manager.py`.

### Day 18 — When does a conversation become a lead?

**Script**

“A phone number and a friendly conversation are not enough for a salesperson to act.

Day eighteen: turning calls into useful outcomes.

After hang-up, my post-call pipeline analyzes the transcript and final memory. Its schema includes extracted details, objections, the next action, and statuses such as interested, qualified, or callback required.

For a property enquiry, that could help someone understand the customer’s budget, preferred location, and timeline.

The challenge is defining qualification with evidence. The agent should not label every polite caller as a strong lead.

Today’s code produces call intelligence; connecting that reliably to an external sales workflow is another step.

What makes a lead qualified in your business?”

**Show:** An illustrative completed-call outcome beside the transcript lines supporting it.

**Code connection:** `server/call/outcome_schema.py` and `server/call/post_call_pipeline.py`.

### Day 19 — “I’ll call tomorrow” is not a scheduled callback

**Script**

“An agent saying ‘I’ll arrange that’ can sound successful while nothing has actually been arranged.

Day nineteen: the gap between language and action.

My outcome schema can record that a callback is needed or a site visit was discussed. That record is useful, but it does not itself create a calendar booking or a CRM task.

The current Tools pages explicitly put CRM and webhook actions after the MVP.

So I need clear language about what the agent can really complete. Until an action is implemented and confirmed, it should record the request and explain the next step accurately.

Which action would save your team the most work: a callback task, appointment, or sales handoff?”

**Show:** “Request captured” → future action service → “Action confirmed.” Mark the future service clearly.

**Code connection:** Outcome dispositions plus `web/app/app/(console)/agents/[id]/tools/page.tsx`. The `site_visit_planned` label is not evidence of a booking integration.

### Day 20 — A lead is useless if it never reaches the team

**Script**

“The call can go perfectly and still fail the business if the result never reaches the salesperson.

Day twenty: planning the CRM connection.

My repository has CRM settings, but the actual webhook and CRM tools are still future work. I am not calling a saved URL a working integration.

The next design needs field mapping, delivery status, retries, and a stable identifier so retrying one outcome does not create duplicate leads.

It also needs to handle the CRM being temporarily unavailable without losing the call result.

That is the hurdle between generating structured information and delivering a dependable workflow.

Which CRM should I use for the first real integration test?”

**Show:** Stored call outcome → proposed delivery queue → CRM acknowledgment, including a failed delivery and retry.

**Code connection:** `server/services/runtime_settings.py`, settings route CRM fields, and the post-MVP Tools page. Queue/retry/idempotency here are proposed implementation work.

### Day 21 — The campaign worker still cannot dial

**Script**

“I found a useful reminder in my own code: a campaign can say ‘running’ before any calling work happens.

Day twenty-one: outbound campaigns.

The backend can create a campaign, import contacts, create a run, and attempt to enqueue it.

But the worker’s processing function currently logs the job. The actual Exotel dialing call is still a comment.

That is different from the separate manual outbound test endpoint, which does contain provider call code.

My next task is connecting the campaign worker to dialing, contact state updates, retry rules, and visible failures when a job cannot be queued.

What campaign status would help you most: queued, dialing, answered, or action required?”

**Show:** Campaign start route → Redis enqueue → worker `process_job()` comment, then the separate outbound test implementation.

**Code connection:** `server/routes/campaigns.py`, `worker/dialer.py:54`, and `server/routes/dev_exotel.py:232`.

### Day 22 — Ten simultaneous calls are a different product

**Script**

“One smooth conversation does not prove the system can handle ten conversations at once.

Day twenty-two: concurrency and background work.

Every call has audio connections, model requests, memory, and finalization work competing for resources.

My repository has PostgreSQL models and Redis infrastructure, but some important runtime state is still held inside one process. Post-call analysis currently uses an in-process queue.

That means I need to design for restarts and multiple workers before claiming dependable scale.

The hurdle is keeping live responses responsive while ensuring recordings and lead outcomes still finish when a process stops.

My next evidence needs to come from load and recovery tests.

What call volume would your business actually need?”

**Show:** Several call lanes, then a process restart and proposed durable recovery path. Label capacity targets as targets.

**Code connection:** `server/call/post_call_pipeline.py`, `server/call/call_context.py`, `worker/main.py`, and `docker-compose.yml`.

### Day 23 — “Do not call me again” is a system requirement

**Script**

“The most important result of a call might be ‘Do not call this person again.’

Day twenty-three: respecting contact preferences.

The repository already has a do-not-call table and APIs. But storing a preference is only the beginning.

Because the campaign worker is unfinished, I still need to connect suppression checks to every outbound attempt and make sure retries cannot bypass them.

The same goes for consent records, calling windows, and stop requests: they need explicit product behavior, not an assumption hidden inside a prompt.

My goal is a system where a clear opt-out changes future calling behavior reliably.

What would make you trust an automated business call more?”

**Show:** Opt-out → suppression record → blocked future attempt as a planned acceptance test.

**Code connection:** `DncEntry` in `server/db/models/phase5_models.py` and DNC APIs in `server/routes/campaigns.py`. Enforcement is unfinished; this is a product-design script, not legal advice or a compliance claim.

### Day 24 — Two customers must never share the wrong data

**Script**

“If two businesses use my platform, one must never be able to open the other’s calls or campaigns.

Day twenty-four: account boundaries.

The code includes tenants, user sessions, and role permissions. Those are the foundations for separating businesses and controlling who can change an agent.

The hard part is applying those boundaries to every operation. I found campaign actions that look up a campaign by its ID without adding the tenant filter used elsewhere.

That is a hardening task to complete before broad customer access.

I also need consistent authentication on telephone stream connections.

The test I want is straightforward: log in as one business and prove another business’s records stay inaccessible.”

**Show:** Two test accounts and an expected access-denied boundary. Do not expose live identifiers or present an unrun test as passing.

**Code connection:** `server/routes/campaigns.py`, `server/auth/rbac.py`, `server/auth/tenant_context.py`, and `server/routes/exotel_ws.py`. The WebSocket currently permits paths without a valid stream token.

### Day 25 — Natural speech should still introduce the agent honestly

**Script**

“I want the agent to sound natural. I also want the person answering to understand who is calling.

Day twenty-five: the first sentence.

One of the current default instructions says the assistant should not mention being AI unless asked. That is a product choice I want to revise before customer-facing calling.

My preferred opening is simple: ‘Hi, I’m the automated assistant for this business. Is now a good time to talk?’

Then the agent can explain the purpose and respect the answer.

The challenge is making that introduction consistent across configured agents and telephone sessions, rather than relying on a single editable line.

Would that introduction make you more comfortable continuing?”

**Show:** Current default instruction and a clearly labeled proposed replacement greeting.

**Code connection:** `server/prompts/voice_defaults.py:14`. The replacement is proposed; it was not applied to the repository. Do not imply the default already performs this introduction.

### Day 26 — A recording should help explain what happened

**Script**

“When a lead looks wrong, I want to trace it back to what was actually said.

Day twenty-six: call investigation.

The platform has transcript ledgers, memory events, audio archives, and call-detail components. Together, they can help connect a final outcome to the conversation behind it.

The hurdle is making that evidence trustworthy. Audio sample rates, interrupted speech, and timing alignment all matter.

The current PSTN bridge converts eight-kilohertz audio to sixteen kilohertz, while the archive has its own agent-audio defaults. I need explicit sample-rate checks across that boundary.

Generated speech also does not prove the caller heard every word.

What would your team need to review before trusting an AI-qualified lead?”

**Show:** Transcript, memory update, and recording panels; illustrate a playback marker versus generated text.

**Code connection:** `server/call/audio_archive.py`, `server/services/audio_transcode.py`, the PSTN bridge, and `web/components/calls/`. Sample-rate and synchronization concerns require runtime verification.

### Day 27 — The latency number can measure the wrong thing

**Script**

“A dashboard can display ‘end-to-end latency’ without measuring when the caller hears the reply.

Day twenty-seven: measuring the right delay.

I found a concrete gap in the live-turn trace: the TTS first-audio field is empty, and the end-to-end field is assigned the brain latency.

That does not capture the full listening-to-speaking journey.

I need timestamps for speech end, final transcript, first model output, first synthesized audio, and playback. Then I can locate the delay instead of guessing which provider is slow.

The challenge is comparing the same measurements across browser and telephone calls.

When I publish a speed claim, I want to show what the timer actually measured.”

**Show:** The current trace assignment, then a proposed latency waterfall with unmeasured stages visibly blank.

**Code connection:** `server/call/live_turn_orchestrator.py:371` and Test Studio latency components. No achieved latency claim is supported by this review.

### Day 28 — The benchmark screen is ahead of the runner

**Script**

“A benchmark screen can look complete before it runs a single real comparison.

Day twenty-eight: testing different voice stacks.

My platform has provider choices, stack tiers, and benchmark scenarios for greetings, enquiries, callbacks, and language switching.

But the current benchmark start function creates result skeletons. The metrics are empty, and the code explicitly says the automated runner is not wired.

So I cannot use that screen to claim one stack is faster or better.

The next step is running the same scenarios through the actual pipeline and recording latency, field accuracy, reliability, and total cost.

Which would matter most in your decision: accurate details, natural speech, speed, or cost?”

**Show:** `runner_note`, `pending_runner`, and empty metrics, followed by the proposed comparison criteria.

**Code connection:** `server/benchmark/session_store.py:80`, `server/routes/benchmarks.py`, and `server/providers/resolver.py`.

### Day 29 — “Works on localhost” cannot answer a telephone call

**Script**

“My browser reaching the backend does not mean the telephone provider can reach it.

Day twenty-nine: deployment.

For the phone path, Exotel needs a publicly reachable callback and WebSocket endpoint. The frontend, API, database, storage, and worker also need the right configuration in their deployment environment.

The repository has deployment files, health checks, and tunnel scripts, but those files alone do not prove the full calling journey works after a release.

The hurdle is verifying the deployed path: connection, speech, interruption, hang-up, recording, and outcome.

I want visible failures and a recovery plan when any of those steps breaks.

Which part of that live deployment test should I show in detail?”

**Show:** Deployment topology and an unfilled release checklist, then actual results when available.

**Code connection:** `railway.json`, `Dockerfile.api`, `Dockerfile.worker`, `server/config/urls.py`, and tunnel scripts. Deployment configuration is not evidence of a successful production launch.

### Day 30 — The demo that has to prove the whole journey

**Script**

“After 30 days of showing the architecture, here is the test I want this platform to pass.

A business configures an agent. An opted-in tester answers a real telephone call. The agent introduces itself, asks useful questions, handles a correction, and respects an interruption.

After hang-up, the platform shows the transcript, captured requirements, qualification evidence, and a clear next action.

If CRM delivery is ready, I’ll show the acknowledgment. If it is not, I’ll show the saved outcome and name that gap.

The next work is already clear: telephone streaming, reliable campaign execution, durable background processing, and measured results.

If your business wants to help test this with permission-based enquiries, tell me your use case.”

**Show:** A consented end-to-end demonstration if available. Otherwise show the intended acceptance flow and label missing stages. Use actual failures and measured results, including an inconclusive outcome, rather than an edited success montage.

**Code connection:** This combines the website, Exotel bridge, lifecycle, memory, outcome, and future delivery path. Do not claim these milestones were achieved merely because day 30 arrived.

## Source anchors for the code review

All links below are pinned to the inspected commit rather than a moving branch.

- [Frontend dependencies](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/web/package.json) and [backend dependencies](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/pyproject.toml).
- [Exotel outbound test endpoint](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/routes/dev_exotel.py#L232).
- [PSTN bridge: complete-reply buffering](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/services/exotel_pstn_bridge.py#L173) and [audio buffering](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/services/exotel_pstn_bridge.py#L233).
- [PSTN interruption logic](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/services/exotel_pstn_bridge.py#L132) and [WebSocket access checks](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/routes/exotel_ws.py#L15).
- [Browser TTS pipeline](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/web/lib/voice/turn-tts-pipeline.ts#L82) and [text chunker](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/web/lib/voice/text-chunker.ts#L21).
- [Provider registry](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/providers/registry.py) and [stack resolver](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/providers/resolver.py).
- [Business brain sections](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/brain/sections.py), [call version locking](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/call/call_lifecycle_service.py#L101), and [version-lock tests](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/tests/test_call_version_lock.py).
- [Memory manager](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/call/memory_manager.py) and [compact memory projection](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/call/memory_projection.py).
- [Outcome schema](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/call/outcome_schema.py) and [in-process post-call queue](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/call/post_call_pipeline.py#L23).
- [Campaign APIs](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/routes/campaigns.py) and [worker dialing scaffold](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/worker/dialer.py#L54).
- [Post-MVP CRM/tools page](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/web/app/app/%28console%29/agents/%5Bid%5D/tools/page.tsx).
- [Current default identity instruction](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/prompts/voice_defaults.py#L14).
- [Incomplete trace timing fields](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/call/live_turn_orchestrator.py#L371).
- [Benchmark result skeletons](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/server/benchmark/session_store.py#L80).
- [Existing CI workflow](https://github.com/MOHAN8897/voice-agent/blob/4956d211a1e7d36cf39953a1a53e77774f80a031/.github/workflows/ci.yml). This review does not establish its latest result.

## External technical references

These verify the protocol concepts used in the explanation. They are not evidence of this repository's runtime performance or customer outcomes.

- Exotel documents bidirectional Voicebot events, PCM audio, configurable sample rates, playback marks, and the `clear` event: [AgentStream WebSocket protocol](https://developer.exotel.com/docs/agentstream/websocket-protocol).
- Sarvam documents interim/final transcripts and VAD configuration for real-time recognition: [Realtime Streaming Speech-to-Text API](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming).
- Sarvam documents STT modes including code-mixed transcription: [Streaming Speech-to-Text API](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/streaming-api). Supported vendor models may have changed since this repository snapshot; no provider migration is implied here.

## Recording notes

Use the hook immediately, then show one relevant screen, code excerpt, or diagram. Keep technical explanations attached to a customer consequence. Aim for a natural delivery; trim a sentence if the visual needs extra time.

The scripts use customer pains as scenarios to investigate: missed enquiries, repeated questions, inaccurate requirements, unfulfilled callback promises, lost CRM handoffs, unwanted repeat calls, and unclear costs. They do not assert market-wide prevalence or use invented conversion statistics.

Use the specific daily audience invitation instead of repeating “follow for more.” When showing logs or calls, use test data or permissioned material and hide private details. Keep “implemented,” “observed in a live test,” and “planned” visibly distinct.
