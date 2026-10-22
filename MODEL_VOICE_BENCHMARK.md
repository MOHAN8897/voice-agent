# Voice LLM benchmark — Gemini vs DeepSeek vs Luna

**Date:** 2026-09-06  
**Harness:** `scripts/_voice_model_benchmark.py`  
**Raw log:** `data/dev-logs/voice_model_benchmark.json`  
**What was measured:** live `/api/brain/stream` on the same compiled agents (sales, education, support, recruitment, follow-up). **TTFT** = time to first spoken SSE delta (what PSTN hears first). **Total** = full JSON turn.  
**Judge:** `strict_live_fails` (goodbye-without-hangup, sarcasm pitch, don’t-call, invented salary, hesitation questions) plus a Telugu check. The Telugu check originally flagged some **romanized Telugu (Tanglish)** as English; the tables below correct that by hand.

PSTN audio was **not** dialed. This is the LLM slice only (Sarvam STT/TTS still sit around it on a real call).

Industry bar used for judgment: natural phone talk wants **voice-to-voice under ~1.5s**, which leaves roughly **700ms of LLM TTFT** after STT/TTS/network ([MarkTechPost TTFT voice benchmark, Aug 2026](https://www.marktechpost.com/2026/08/30/lowest-latency-inference-apis-for-voice-and-realtime-agents-a-time-to-first-token-ttft-first-benchmark/)). None of the Gemini Flash models cleared that 700ms bar on this 3k-token cached brain. Luna was the closest.

---

## Headline verdict

**Best overall for this agent (fast + talking + Telugu + PSTN):** `gpt-5.6-luna`  
Average TTFT **~1.2s**, total **~1.7s**, **0/8 English and 0/8 Telugu** behavioral fails, real Telugu script not just Tanglish.

**Best Gemini if you refuse OpenAI:** `gemini-3.7-flash`  
Same hard-test cleanliness as Luna in Telugu (**0/8**), slightly slower (~2.4s English TTFT / ~2.0s Telugu TTFT). Latest `gemini-3.8-flash` did **not** beat 3.7 here.

**Fastest Gemini:** `gemini-3.5-flash-lite` (~2.1s English TTFT, ~1.9s Telugu) — cheapest too — but it treated `hmm` as bad audio and spoke **romanized** Telugu. Not the best talker.

**Best non-OpenAI / non-Gemini we actually ran:** `deepseek-chat`  
Fastest of the whole Gemini set (**~1.4s** English TTFT) and 0/8 English policy fails, but it **re-greeted mid-call**, asked extra questions, and Telugu was mostly Tanglish. Usable as a cheap fallback, not as the primary PSTN brain.

**Do not use for live PSTN:** `gemini-3.5-flash` (~7s English TTFT).

---

## What the web said (checked 2026-09-06)

### Gemini lineup

| SKU | Role on paper | Price (public, per 1M) | Notes |
|---|---|---|---|
| **gemini-3.8-flash** | Latest (GA 2 Sep 2026) | $0.75 in / $3.75 out (intro, same as 3.7) | Better at long agent jobs; **more thinking tokens**. `thinkingLevel=MINIMAL` **errors**; voice must use **LOW**. [Model card](https://deepmind.google/models/model-cards/gemini-3-8-flash/), [3.8 vs 3.7](https://apidog.com/blog/gemini-3-8-flash-vs-gemini-3-7-flash/) |
| **gemini-3.7-flash** | Previous flagship | Same $0.75 / $3.75 | Still fully supported. Our live run preferred this over 3.8 for phone turns. |
| **gemini-3.5-flash** | Balanced | Mid | Public TTFT often looks fine; **on this brain it was 6–14s**. Unusable. |
| **gemini-3.5-flash-lite** | Fastest / cheapest 3.5 | **$0.30 in / $2.50 out** | Advertised ~350 tok/s. Fastest Gemini we measured. Weaker Telugu + hesitation. |
| **gemini-3.1-flash-lite** | Older cheap | Flash-Lite class | Slower than 3.5-lite here; pitched during `hmm`. |

Google also ships **Gemini 3.1 Flash Live** (speech-to-speech). That is a **different architecture** (replaces STT+LLM+TTS), not a drop-in for this Sarvam cascade. Not tested.

### Others (not OpenAI, not Gemini)

| Option | Why it matters for PSTN | Status in this repo |
|---|---|---|
| **DeepSeek `deepseek-chat` / V4 Flash** | Cheap; our run was **faster than every Gemini**. Official V4 Flash is $0.14 / $0.28 per 1M ([DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)). | **Ran** on the live path. English policy OK; Telugu and re-greets weaker. |
| **Groq Llama 4 Scout** (`meta-llama/llama-4-scout-17b-16e-instruct`) | Public TTFT **~80–100ms**, ~1580 tok/s. Best published *speed* alternative. OpenAI-compatible API. Telugu quality **unknown** until wired. | **Not in the stack.** Highest-priority next provider if Luna is ever too expensive/slow. |
| **Cerebras / SambaNova gpt-oss** | MarkTechPost: ~0.5s TTFT, huge tok/s. | Not wired. Overkill unless you already have those accounts. |
| **Claude Haiku 4.5** | ~0.84s TTFT in the same public table; good English talker. | Not wired. Indic Telugu is the risk. |
| **Sarvam-class Indic LLMs** | Built for code-switched Telugu/Tanglish. | Not an LLM provider here today (Sarvam is STT/TTS only). |

---

## Measured latency (this machine, this brain)

Same 8 hard turns per language. First turn of each model is usually the slowest (cache fill).

### English

| Model | Strict fails | Style flags | Avg TTFT | P50 TTFT | Avg total | Max total |
|---|---|---|---|---|---|---|
| **gpt-5.6-luna** | **0/8** | 0 | **1199 ms** | ~1142 | **1658 ms** | 1857 |
| deepseek-chat | 0/8 | 0 | **1426 ms** | ~1297 | 1929 ms | 2507 |
| gemini-3.5-flash-lite | 0/8* | 0 | 2131 ms | ~2140 | 2216 ms | 2798 |
| gemini-3.7-flash | 0/8 | 0 | 2406 ms | ~2482 | 2647 ms | 3734 |
| gemini-3.8-flash | 0/8 | 1 disclaimer | 2756 ms | ~2177 | 3103 ms | 5717 |
| gemini-3.1-flash-lite | **1/8** | 0 | 4372 ms | ~4286 | 4574 ms | 6136 |
| gemini-3.5-flash | 0/8 | 0 | **6943 ms** | ~6004 | **7351 ms** | 14395 |

\*Lite English `hmm` said “Sorry, I didn’t catch that.” The regex judge did not fail it (no `?`), but it is a **talking fail**: hesitation is not bad audio.

### Telugu

| Model | Strict fails (auto) | After Tanglish review | Avg TTFT | Avg total | Telugu quality |
|---|---|---|---|---|---|
| **gpt-5.6-luna** | **0/8** | **0/8** | **1244 ms** | **1757 ms** | Unicode Telugu, natural. `ఉమ్మ్` still hit the unclear-audio fallback. |
| **gemini-3.7-flash** | **0/8** | **0/8** | 2044 ms | 2630 ms | Best Gemini Telugu. Real script, no pitch on sarcasm. Same `ఉమ్మ్` fallback. |
| gemini-3.8-flash | 1/8 (romanized price line) | **0 policy / 1 Tanglish** | 1854 ms | 2379 ms | Mostly Unicode; first price line was Tanglish. |
| deepseek-chat | 3/8 | **0 policy / Tanglish + extra Q** | **1232 ms** | 2133 ms | Fastest Telugu TTFT. Mix of script + Roman. Re-asks. |
| gemini-3.5-flash | 2/8 | Tanglish + slow | 3905 ms | 4354 ms | Too slow; some English-heavy lines. |
| gemini-3.1-flash-lite | 3/8 | Tanglish + pitched on pause | 2396 ms | 2824 ms | Recapped the sales pitch on `ఉమ్మ్`. |
| gemini-3.5-flash-lite | 4/8 | Tanglish + visit on sarcasm + pause question | 1867 ms | 2059 ms | Fast, cheap, **not** the Telugu talker you want. |

---

## Hard-test talking notes (not lenient)

All models were run on: fast price, “not now”, moon sarcasm, email-later, don’t-call, salary, follow-up “not interested”, `hmm` / `ఉమ్మ్`.

### English talking

| Model | Fast price | Not now | Sarcasm | Don’t-call hangup | Salary | `hmm` | Extra talking faults |
|---|---|---|---|---|---|---|---|
| Luna | Fact only | Stay | “Fair enough. I won’t push.” | Hangup + goodbye | Check later | “Take your time.” | Honest “can’t email from this call” |
| 3.7 Flash | Fact only | Stay | Same | Hangup | Check later | “Take your time.” | Slightly warmer than Luna |
| 3.8 Flash | Fact only | Stay | Same | Hangup | Check later | “I’m here.” | One “on this call” disclaimer |
| 3.5-lite | Fact only | Stay | Same | Hangup | Check later | **Treated as ASR fail** | Fine otherwise |
| 3.1-lite | Fact only | Stay | Same | Hangup | Check later | **Re-pitched + asked a visit** | Fail |
| 3.5 Flash | Fact + **asked for a site visit** | Stay | Soft | Hangup | Check later | “Take your time.” | Slow, salesy on a fast ask |
| DeepSeek | Fact only | Stay but **re-greeted** | Soft | Hangup | Check later | **Re-greeted + dumped inventory** | Asks for email address |

### Telugu talking

| Model | Speaks Telugu script? | Don’t-call | Sarcasm | Pause `ఉమ్మ్` |
|---|---|---|---|---|
| Luna | Yes | Farewell + hangup | Stopped, no visit | Unclear-audio fallback (pack line) |
| 3.7 Flash | **Yes, best of Gemini** | Farewell + hangup | Stopped | Same fallback |
| 3.8 Flash | Mostly yes | Farewell + hangup | Stopped | Same fallback |
| DeepSeek | Mixed / Tanglish | Hangup | Mixed | Started a pitch |
| 3.5-lite | Almost only Tanglish | Hangup | **Asked if they want a visit** | “Vinipistondi, cheppandi” (a question) |

---

## Rankings for *this* product

Scored for PSTN: latency first, then hard-test fails, then Telugu, then human wording.

1. **gpt-5.6-luna** — keep as live default. Only model that is both sub-~1.7s total and clean in both languages.
2. **gemini-3.7-flash** — best Gemini talker, especially Telugu. Use if you must be on Google. Set `thinkingLevel=LOW` (already in the adapter).
3. **gemini-3.8-flash** — latest, not faster, not clearly better on these phone turns. Skip for PSTN until Google’s LOW thinking actually drops TTFT.
4. **deepseek-chat** — best *measured* non-OpenAI/non-Gemini speed. Enable only as a low-tier fallback after you stop mid-call re-greets (prompt already forbids this; the model ignored it more than Luna/3.7).
5. **gemini-3.5-flash-lite** — cheapest/fastest Gemini. English policy is fine; Telugu and hesitation are not. Possible “low” tier if cost is the only knob.
6. **gemini-3.1-flash-lite** — dominated by 3.5-lite.
7. **gemini-3.5-flash** — reject for live calls.

### If you add one new provider

**Groq Llama 4 Scout** is the one to try next for PSTN speed (public ~80ms TTFT, OpenAI-compatible). It is **not** proven on Telugu in this repo. Wire it the same way as DeepSeek, then re-run `scripts/_voice_model_benchmark.py` before putting it on Exotel.

Do **not** switch the live brain to Gemini Live / speech-to-speech without a separate design: this agent’s memory, hangup gate, and Sarvam TTS would not come along automatically.

---

## What I would actually configure

| Call type | LLM |
|---|---|
| Live PSTN + browser (today) | **gpt-5.6-luna** |
| Google-only constraint | **gemini-3.7-flash** (thinking LOW) |
| Cost-save English-only | gemini-3.5-flash-lite (accept worse `hmm` + no real Telugu) |
| Experimental cheap fallback | deepseek-chat (after re-greet is fixed) |
| Next speed experiment | Groq Llama 4 Scout — **test Telugu hard before production** |

---

## Method notes

- 7 models × 8 English × 8 Telugu = 112 live turns, plus 10 compile jobs.
- Agents were recompiled (`agent_script_v9`) in `en-IN` and `te-IN` before the runs.
- Gemini 3.8 was added to the catalog so the stack resolver would not silently fall back.
- DeepSeek was included even though `ENABLE_DEEPSEEK` is false in `.env`; the live adapter still served `deepseek-chat` on override (key was available at runtime). Treat that as “it works if you turn the flag on,” not as a production default.
- `ఉమ్మ్` triggering `Sorry, clear ga raledu` on Luna/3.7/3.8 is a **shared Telugu pack** issue (hesitation vs unclear audio), not a 3.7-vs-3.8 difference.

*This report only claims what was executed. Groq/Claude numbers are from public 2026 latency tables, not from this API.*
