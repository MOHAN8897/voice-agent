"""Build business-brain draft sections from SaaS onboarding output."""
from __future__ import annotations

import json
from typing import Any

from server.services.saas.script_variables import SAAS_SCRIPT_VARIABLES_TITLE

DEFAULT_BOUNDARIES = [
    "Do not invent prices, policies, or appointments not in the script.",
    "Use supplied contact details naturally. Ask for unknown details only when needed for the call's purpose.",
]


def studio_brain_sections(
    *,
    script: str,
    greeting: str,
    role: str,
    language: str,
    variables: list[dict[str, str]],
    boundaries: list[str] | None = None,
    voice_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    lang = language or "te-IN"
    identity = "\n\n".join(
        [
            f"Role: {role or 'Voice agent'}",
            f"Opening greeting: {greeting}",
            "Speak naturally on a live phone call. Keep replies concise.",
        ]
    )
    guard = "\n".join(f"- {b}" for b in (boundaries or DEFAULT_BOUNDARIES))
    voice_cfg = voice_config or {
        "realtimeVoice": "marin",
        "voiceId": "marin",
        "speed": 1.0,
        "language": lang,
        "turnDetection": "semantic_vad",
        "noiseReduction": "far_field",
    }
    return [
        {
            "type": "custom",
            "title": "saas_voice_config",
            "order": 5,
            "raw_text": json.dumps(voice_cfg, indent=0),
            "enabled": True,
        },
        {
            "type": "custom",
            "title": SAAS_SCRIPT_VARIABLES_TITLE,
            "order": 8,
            "raw_text": json.dumps({"version": 1, "variables": variables}, indent=2),
            "enabled": False,
        },
        {
            "type": "identity_purpose",
            "title": "Identity & Purpose",
            "order": 10,
            "raw_text": identity,
            "enabled": True,
        },
        {
            "type": "facts",
            "title": "Business Facts",
            "order": 20,
            "raw_text": script or "",
            "enabled": True,
        },
        {
            "type": "guardrails",
            "title": "Guardrails",
            "order": 30,
            "raw_text": guard,
            "enabled": True,
        },
    ]
