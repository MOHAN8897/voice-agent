"""What a live call actually sends to Gemini, and what it costs.

Measures the compiled brain, then the FULL system instruction the Gemini Live
path builds from it, and prices both with the rates the platform bills by.

Run: PYTHONIOENCODING=utf-8 python -m scripts.live_prompt_cost
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

BRAIN = "C:/Users/subha/AppData/Local/Temp/opencode/live_prompt.txt"
MODEL = "gemini-3.8-live"
# The brain as it stood before the compression pass, for the saving.
BEFORE_TOKENS = 5376


def main() -> int:
    from server.agent.brain_prompt_composer import estimate_tokens
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
    from server.services.usage_pricing import (
        GEMINI_LIVE_AUDIO_TOKENS_PER_SEC,
        cost_llm_usd,
        gemini_audio_rates_for_model,
        gemini_rates_for_model,
    )

    with open(BRAIN, encoding="utf-8") as fh:
        brain = fh.read().strip()

    opening = (
        "Hi, nenu Priya, spandana private limited nundi matladutunnanu. Meeku oka moment unda?"
    )
    instruction = build_gemini_audio_session_instructions(
        brain, language="te-IN", direction="outbound", opening_greeting=opening
    )

    brain_t = estimate_tokens(brain)
    instr_t = estimate_tokens(instruction)
    text_rates = gemini_rates_for_model(MODEL)
    audio_rates = gemini_audio_rates_for_model(MODEL)

    print("=" * 72)
    print(f"model                    {MODEL}")
    print(f"compiled brain           {brain_t:>7,} tokens   ({len(brain):,} chars)")
    print(f"FULL system instruction  {instr_t:>7,} tokens   <-- what Gemini receives")
    print(f"wrapper adds             {instr_t - brain_t:>7,} tokens")
    print("=" * 72)
    print(f"text   in ${text_rates['input']}/1M  out ${text_rates['output']}/1M  cached ${text_rates['cached_input']}/1M")
    print(f"audio  in ${audio_rates['input']}/1M  out ${audio_rates['output']}/1M  cached ${audio_rates['cached_input']}/1M")
    print()

    prompt_cost = instr_t / 1_000_000 * text_rates["input"]
    before_cost = BEFORE_TOKENS / 1_000_000 * text_rates["input"]
    print("PROMPT COST PER CALL SESSION (system instruction, text input)")
    print(f"  before  {BEFORE_TOKENS:>6,} tok  ${before_cost:.6f}")
    print(f"  after   {instr_t:>6,} tok  ${prompt_cost:.6f}")
    print(f"  saved                 ${before_cost - prompt_cost:.6f}  ({(1 - instr_t / BEFORE_TOKENS) * 100:.0f}% smaller)")
    print()

    print(f"AUDIO COST (the part that actually dominates)")
    for minutes in (1, 3, 5):
        sec = minutes * 60
        # Live speech is bidirectional: both sides stream audio in.
        audio_in = GEMINI_LIVE_AUDIO_TOKENS_PER_SEC * sec
        # The agent replies in short bursts; roughly a third of the call is the
        # agent speaking, at a conversational rate.
        audio_out = int(audio_in * 0.35)
        c = cost_llm_usd(
            input_tokens=instr_t + audio_in,
            output_tokens=audio_out,
            input_audio_tokens=audio_in,
            output_audio_tokens=audio_out,
            llm_model=MODEL,
        )
        print(
            f"  {minutes} min: audio in {audio_in:>7,} tok (${c['audio_input_usd']:.4f})"
            f"  out {audio_out:>7,} tok (${c['audio_output_usd']:.4f})"
            f"  prompt ${c['uncached_usd']:.4f}"
            f"  TOTAL ${c['total_usd']:.4f}"
        )
    print()
    print(f"audio token rate used: {GEMINI_LIVE_AUDIO_TOKENS_PER_SEC}/sec per stream")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
