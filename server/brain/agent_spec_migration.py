"""
Migration & Backfill Tool for AgentSpec Pipeline.
Scans stored agents, flags those without a valid spec or containing legacy fallback names (Priya/Alex),
and recompiles them cleanly using the verified AgentSpec pipeline.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from typing import Any

from server.agent.instruction_store import instruction_store
from server.brain.agent_spec import AgentSpec
from server.brain.agent_spec_extractor import extract_agent_spec
from server.brain.agent_spec_script_builder import (
    generate_deterministic_script_from_spec,
    lint_agent_script,
)
from server.brain.agent_script_compiler import (
    _platform_call_rules,
    build_compiler_sections,
    reassemble_brain_from_script,
)
from server.call.call_end_policy import normalize_call_end_policy
from server.agent.brain_prompt_composer import estimate_tokens
from server.services.session_persist import session_persist

logger = logging.getLogger(__name__)

LEGACY_DENYLIST = {"priya", "alex"}


def is_legacy_fallback_present(script: str, brief: str) -> bool:
    """Returns True if the script contains legacy fallback names not mentioned in the brief."""
    b_lower = (brief or "").lower()
    s_lower = (script or "").lower()
    for name in LEGACY_DENYLIST:
        if name in s_lower and name not in b_lower:
            return True
    return False


def audit_agent(session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Audits a single agent record for missing spec or legacy fallback corruption."""
    brief = str(data.get("agentBrief") or data.get("behaviour") or "").strip()
    script = str(data.get("agentScript") or "").strip()
    has_spec = bool(data.get("agentSpec"))
    legacy_detected = is_legacy_fallback_present(script, brief)

    reasons: list[str] = []
    if not has_spec:
        reasons.append("missing_agent_spec")
    if legacy_detected:
        reasons.append("contains_legacy_fallback_name")
    if not script:
        reasons.append("empty_agent_script")

    flagged = bool(reasons)
    return {
        "sessionId": session_id,
        "hasSpec": has_spec,
        "hasLegacyFallback": legacy_detected,
        "flagged": flagged,
        "reasons": reasons,
        "specVersion": data.get("specVersion"),
        "templateVersion": data.get("templateVersion"),
        "language": data.get("language") or "te-IN",
    }


def audit_all_agents() -> list[dict[str, Any]]:
    """Audits all agents currently in disk persistence."""
    all_inst = session_persist.all_instructions()
    results = []
    for sid, data in all_inst.items():
        if isinstance(data, dict):
            results.append(audit_agent(sid, data))
    return results


async def recompile_agent(session_id: str, *, force: bool = False) -> dict[str, Any]:
    """Recompiles an agent record from its brief using the verified AgentSpec pipeline."""
    meta = instruction_store.get_with_meta(session_id)
    brief = str(meta.get("agentBrief") or meta.get("behaviour") or "").strip()
    if not brief:
        return {"sessionId": session_id, "ok": False, "error": "Agent brief is empty; cannot recompile."}

    language = meta.get("language") or "te-IN"
    spec = await extract_agent_spec(brief, language_code=language)

    if spec.needs_user_input and not force:
        return {
            "sessionId": session_id,
            "ok": False,
            "error": f"Agent recompile blocked: needs user input for {spec.needs_user_input}",
            "needsUserInput": spec.needs_user_input,
        }

    script = generate_deterministic_script_from_spec(spec, direction="outbound")
    lint_issues = lint_agent_script(script, spec)

    role = spec.call_objective.value if spec.call_objective else "sales"
    agent_name_val = spec.agent_name.value if spec.agent_name else "Agent"
    policy = normalize_call_end_policy(meta.get("callEndPolicy"), language=language)
    platform_rules = _platform_call_rules(
        agent_name=agent_name_val,
        role=role,
        direction="outbound",
        language=language,
    )
    _script, compiled = reassemble_brain_from_script(
        script=script,
        language=language,
        style=meta.get("style"),
        call_end_policy=policy,
        platform_call_rules=platform_rules,
        agent_name=agent_name_val,
        role=role,
    )

    optimizer_report = {
        "agent_name": agent_name_val,
        "detected_role": role,
        "platform_call_rules": platform_rules,
        "script_warnings": lint_issues,
        "extraction_source": spec.extraction_source,
        "spec_hash": spec.spec_hash(),
        "recompiled_at": "backfill",
    }
    budget = int(meta.get("budgetTokens") or 2500)
    est = estimate_tokens(compiled)
    if est > budget:
        budget = est

    saved = instruction_store.save_agent_script(
        session_id,
        brief,
        script,
        meta.get("style"),
        compiled_brain=compiled,
        optimizer_report=optimizer_report,
        source_checksum=spec.spec_hash(),
        language=language,
        budget_tokens=budget,
        raw_token_estimate=est,
        call_end_policy=policy,
        agent_spec=spec.model_dump(),
        spec_version=1,
        template_version=1,
        prompt_version=1,
        model_name=spec.extraction_source,
    )
    await instruction_store.persist_to_db(session_id)
    return {
        "sessionId": session_id,
        "ok": True,
        "specHash": spec.spec_hash(),
        "agentName": agent_name_val,
        "extractionSource": spec.extraction_source,
    }


async def recompile_all_flagged_agents(*, force: bool = False) -> dict[str, Any]:
    """Audits and recompiles all flagged agents."""
    audits = audit_all_agents()
    flagged = [a for a in audits if a["flagged"]]
    recompiled = 0
    skipped = 0
    details = []

    for item in flagged:
        sid = item["sessionId"]
        res = await recompile_agent(sid, force=force)
        details.append(res)
        if res.get("ok"):
            recompiled += 1
        else:
            skipped += 1

    return {
        "total_audited": len(audits),
        "total_flagged": len(flagged),
        "recompiled": recompiled,
        "skipped": skipped,
        "details": details,
    }


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="AgentSpec Backfill & Recompile CLI")
    parser.add_argument("--audit", action="store_true", help="Audit all agents and display flagged list")
    parser.add_argument("--recompile", action="store_true", help="Recompile all flagged agents")
    parser.add_argument("--force", action="store_true", help="Force recompile even if needs_user_input")
    args = parser.parse_args()

    if args.recompile:
        result = asyncio.run(recompile_all_flagged_agents(force=args.force))
        print(json.dumps(result, indent=2))
    else:
        results = audit_all_agents()
        flagged = [r for r in results if r["flagged"]]
        print(f"Audited {len(results)} agents. Flagged: {len(flagged)}")
        print(json.dumps(flagged, indent=2))


if __name__ == "__main__":
    cli_main()
