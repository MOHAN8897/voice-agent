from server.call.outcome_schema import merge_outcome_facts


def test_outbound_uses_callee_not_caller_id_for_phone_fallback():
    facts = merge_outcome_facts(
        {},
        {},
        caller_id="+13526146416",
        callee_e164="+918897908470",
        direction="outbound",
    )
    assert facts["phone"] == "+918897908470"


def test_inbound_uses_caller_id_for_phone_fallback():
    facts = merge_outcome_facts(
        {},
        {},
        caller_id="+918897908470",
        callee_e164="+13526146416",
        direction="inbound",
    )
    assert facts["phone"] == "+918897908470"
