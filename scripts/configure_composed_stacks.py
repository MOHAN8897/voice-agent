"""Create missing development Low/Standard drafts and supplier rates safely.

Run without --apply to inspect the plan. Existing mappings and Premium are kept.
Release evidence and customer retail prices remain separate admin decisions.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def configure(*, apply: bool) -> dict:
    from sqlalchemy import select

    from server.db.connection import close_db, get_session_factory, init_db
    from server.db.models.entities import TierAssignment
    from server.services.dev_runtime import effective_app_environment
    from server.services.dev_secrets_store import dev_secrets_store
    from server.services.saas.composed_costing import seed_default_provider_costs
    from server.services.saas.platform_phone_stack import resolve_platform_phone_stack
    from server.services.saas.voice_stack_defaults import recommended_composed_profile
    from server.services.saas.voice_stack_profiles import load_profile_records, save_composed_profile

    environment = effective_app_environment()
    if environment != "development":
        raise RuntimeError("This setup command is restricted to development.")
    plan = {"environment": environment, "applied": apply, "tiers": {}}
    for tier in ("low", "medium"):
        profile = recommended_composed_profile(tier)
        model = profile["engines"][0]["models"][0]
        plan["tiers"][tier] = {"stt": profile["stt"], "llm": profile["llm"],
                               "tts": {key: model[key] for key in ("provider", "model", "apiMode")},
                               "voices": len(model["voices"])}
    if not apply:
        return plan
    if not await init_db():
        raise RuntimeError("A durable development database is required.")

    async def premium_fingerprint() -> str:
        async with get_session_factory()() as session:
            row = (await session.execute(select(TierAssignment).where(
                TierAssignment.environment == environment, TierAssignment.tier == "premium"
            ))).scalar_one_or_none()
            payload = {"tier": row.stack_payload if row else None,
                       "universal": await resolve_platform_phone_stack("te-IN")}
            return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    try:
        before = await premium_fingerprint()
        for field, model in (("sarvam_llm_models_csv", "sarvam-105b-conversations"),
                             ("gemini_tts_models_csv", "gemini-3.8-flash-lite-tts")):
            from server.config.env import get_settings

            current = dev_secrets_store.effective(field, getattr(get_settings(), field, ""))
            models = list(dict.fromkeys([*(part.strip() for part in str(current or "").split(",") if part.strip()), model]))
            dev_secrets_store.update({field: ",".join(models)})
        records = await load_profile_records(environment)
        for tier in ("low", "medium"):
            if tier in records:
                plan["tiers"][tier]["action"] = "preserved existing profile"
                continue
            result = await save_composed_profile(environment=environment, tier=tier, expected_revision=0,
                payload=recommended_composed_profile(tier), actor="composed-stack-setup")
            plan["tiers"][tier].update(action="created disabled draft", revision=result["profileRevision"])
        costs = await seed_default_provider_costs(actor="composed-stack-setup",
            reason="Published supplier tariffs verified 2026-10-22; customer retail rates unchanged")
        plan["providerCostVersion"] = costs["version"]
        plan["premiumUnchanged"] = before == await premium_fingerprint()
        if not plan["premiumUnchanged"]:
            raise RuntimeError("Premium fingerprint changed during setup; inspect concurrent configuration activity.")
        return plan
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(configure(apply=args.apply)), indent=2))
