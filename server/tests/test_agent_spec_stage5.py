"""
Stage 5 Tests: Storage of Spec/Versions/Model, Migration/Audit/Recompile Tool, and Metrics/Shadow Mode.
"""
import pytest
from server.agent.instruction_store import instruction_store
from server.brain.agent_spec_metrics import spec_metrics
from server.brain.agent_spec_migration import audit_agent, recompile_agent


def test_spec_metrics_records_extractions_and_aggregates():
    spec_metrics.reset()

    # Record 3 extractions: 1 gemini, 1 openai, 1 regex fallback with failure
    spec_metrics.record_extraction(source="llm_gemini", duration_sec=1.2, verifier_passed=True, needs_user_input=False)
    spec_metrics.record_extraction(source="llm_openai", duration_sec=0.8, verifier_passed=True, needs_user_input=False)
    spec_metrics.record_extraction(source="regex_fallback", duration_sec=0.1, verifier_passed=False, needs_user_input=True)

    summary = spec_metrics.get_summary()
    assert summary["total_extractions"] == 3
    assert summary["sources"]["llm_gemini"] == 1
    assert summary["sources"]["llm_openai"] == 1
    assert summary["sources"]["regex_fallback"] == 1
    assert summary["verifier_failures"] == 1
    assert summary["needs_user_input_count"] == 1
    assert summary["fallback_count"] == 1
    assert 0.6 < summary["avg_duration_sec"] < 0.8


def test_spec_metrics_shadow_comparison():
    spec_metrics.reset()
    spec_metrics.record_shadow_comparison(
        session_id="sess-1",
        old_agent_name="Priya",
        new_agent_name="Sindhuja",
        discrepancy=True,
    )
    spec_metrics.record_shadow_comparison(
        session_id="sess-2",
        old_agent_name="Sindhuja",
        new_agent_name="Sindhuja",
        discrepancy=False,
    )
    summary = spec_metrics.get_summary()
    assert summary["shadow_comparisons"] == 2
    assert summary["shadow_discrepancies"] == 1


@pytest.mark.asyncio
async def test_agent_spec_audit_flags_and_recompiles_legacy_agent():
    session_id = "test-migration-backfill-sid"
    instruction_store.clear(session_id)

    # 1. Store a corrupt legacy agent with fabricated 'Priya' and no AgentSpec
    brief = (
        "We sell flats and plots. Ask which project they are interested in, their budget "
        "and preferred configuration, then book a site visit. business name is mohan private limited "
        "and the person who calls the users is sindhuja and business location is in hyderabad. vanasthalipuram."
    )
    corrupted_script = (
        "--- AGENT IDENTITY ---\n"
        "You are Priya, representing mohan private limited. Always speak as Priya.\n"
        "--- COMPANY & OFFER ---\n"
        "We sell flats and plots.\n"
    )
    instruction_store.save_agent_script(
        session_id,
        brief,
        corrupted_script,
        style="concise",
        compiled_brain=corrupted_script,
        optimizer_report={"agent_name": "Priya"},
        source_checksum="legacy123",
        language="te-IN",
    )

    data = instruction_store.get_with_meta(session_id)
    assert data["agentSpec"] is None

    # 2. Audit should flag the agent for missing spec and legacy fallback Priya
    audit_res = audit_agent(session_id, data)
    assert audit_res["flagged"] is True
    assert "missing_agent_spec" in audit_res["reasons"]
    assert "contains_legacy_fallback_name" in audit_res["reasons"]

    # 3. Recompile the agent
    recompile_res = await recompile_agent(session_id, force=True)
    assert recompile_res["ok"] is True
    assert recompile_res["agentName"] == "Sindhuja"

    # 4. Check that agent now has full spec, versioning, and zero Priya
    updated_meta = instruction_store.get_with_meta(session_id)
    assert updated_meta["agentSpec"] is not None
    assert updated_meta["agentSpec"]["agent_name"]["value"] == "Sindhuja"
    assert updated_meta["specVersion"] == 1
    assert updated_meta["templateVersion"] == 1
    assert updated_meta["promptVersion"] == 1
    assert "Priya" not in updated_meta["agentScript"]
    assert "Sindhuja" in updated_meta["agentScript"]

    # 5. Re-audit should now be completely clean
    re_audit = audit_agent(session_id, updated_meta)
    assert re_audit["flagged"] is False
    assert re_audit["hasSpec"] is True
    assert re_audit["hasLegacyFallback"] is False

    instruction_store.clear(session_id)
