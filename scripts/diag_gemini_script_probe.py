#!/usr/bin/env python3
"""Compare OpenAI vs Gemini voice prompts and optionally probe Gemini text adherence."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Repo root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _compile_sample_brief(language: str) -> str:
    from server.brain.agent_script_compiler import compile_agent_from_brief

    brief = (
        "Agent Priya from Bindusara Agencies, real estate plots near Hyderabad ORR. "
        "Outbound sales. Opening: Hi, nenu Priya, Bindusara Agencies nundi call chestunnanu. Time unda?"
    )
    compiled, _result, _raw, comp_t, _budget = await compile_agent_from_brief(
        brief=brief,
        language=language,
        use_llm=False,
        budget_tokens=3500,
    )
    print(f"compiled_brain_tokens~{comp_t}")
    return compiled


def _print_prompt_stats(compiled: str, language: str) -> None:
    from server.agent.brain_prompt_composer import estimate_tokens
    from server.realtime.gemini_audio_session import condense_compiled_brain_for_gemini
    from server.realtime.text_session import build_audio_session_instructions
    from server.realtime.voice_instructions import build_realtime_voice_instructions

    opening = "Hi, nenu Priya, Bindusara Agencies nundi call chestunnanu. Time unda?"
    openai = build_realtime_voice_instructions(
        compiled,
        model="gpt-realtime-2.1-mini",
        stack_override={"llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"}},
        language=language,
        direction="outbound",
        opening_greeting=opening,
    )
    gemini = build_realtime_voice_instructions(
        compiled,
        model="gemini-3.8-live",
        stack_override={"llm": {"provider": "gemini", "model": "gemini-3.8-live"}},
        language=language,
        direction="outbound",
        opening_greeting=opening,
    )
    deduped = condense_compiled_brain_for_gemini(compiled)
    print(f"raw_brain_tokens~{estimate_tokens(compiled)} deduped~{estimate_tokens(deduped)}")
    print(f"openai_voice_system_tokens~{estimate_tokens(openai)}")
    print(f"gemini_voice_system_tokens~{estimate_tokens(gemini)}")
    print(f"delta_tokens={estimate_tokens(openai) - estimate_tokens(gemini)}")


async def _probe_gemini_text(compiled: str, language: str, user_line: str) -> None:
    from server.realtime.voice_instructions import build_realtime_voice_instructions

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("GEMINI_API_KEY not set — skipping live probe")
        return
    system = build_realtime_voice_instructions(
        compiled,
        model="gemini-3.8-live",
        stack_override={"llm": {"provider": "gemini", "model": "gemini-3.8-live"}},
        language=language,
        direction="outbound",
        opening_greeting="time unda?",
    )
    from google import genai

    client = genai.Client(api_key=key)
    from server.config.env import get_settings

    model = os.environ.get("GEMINI_PROBE_MODEL") or get_settings().gemini_model
    prompt = (
        f"{system}\n\n---\nSimulated phone turn. Opening was already played. "
        f"Caller says: {user_line}\nReply in audio script style (text only here):"
    )
    resp = client.models.generate_content(model=model, contents=prompt)
    text = (getattr(resp, "text", None) or "").strip()
    print(f"probe_model={model}")
    print(f"caller={user_line!r}")
    print(f"model_reply={text!r}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", default="te-IN")
    parser.add_argument(
        "--user",
        default="Who is this? I don't have time.",
        help="Simulated callee utterance",
    )
    parser.add_argument("--live", action="store_true", help="Call Gemini generateContent if API key set")
    args = parser.parse_args()
    compiled = await _compile_sample_brief(args.language)
    _print_prompt_stats(compiled, args.language)
    if args.live:
        await _probe_gemini_text(compiled, args.language, args.user)


if __name__ == "__main__":
    asyncio.run(main())
