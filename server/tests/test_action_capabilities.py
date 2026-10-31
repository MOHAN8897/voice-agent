"""F10: capabilities are typed metadata, never inferred from translated prose."""
from __future__ import annotations

from server.brain.capabilities import (
    capabilities_section_present,
    order_confirmation_allowed,
    order_confirmation_allowed_from_script,
    order_confirmation_evidence,
    render_capabilities_section,
)
from server.brain.compiled_brain_artifact import (
    assemble_unified_brain,
    business_from_unified_brain,
    refresh_platform_sections,
)
from server.call.order_confirmation import order_workflow_active

QUOTE_ONLY_TE = (
    "ప్రింటెడ్ విజిటింగ్ కార్డ్స్ ఒక్కో కార్డ్ 25 రూపాయలు మరియు కనిష్టంగా 100 కార్డ్స్ "
    "ఆర్డర్ చేయాలి. కొటేషన్ అభ్యర్థన కోసం పేరు మరియు డెలివరీ ప్రాంతాన్ని తీసుకోండి. "
    "ఎలాంటి ఇంటిగ్రేషన్ లేకపోతే CRM డెలివరీ లేదా కన్ఫర్మ్ అయిన ఆర్డర్‌ను క్లెయిమ్ చేయలేరు."
)
QUOTE_ONLY_EN = (
    "Visiting cards cost 25 rupees each with a minimum order of 100 cards. Take the name "
    "and delivery area for a quote request. With no integration we cannot claim CRM "
    "delivery and we cannot confirm an order."
)
ORDER_TAKING_EN = (
    "We take orders for custom invitations. Collect the quantity, the customer name and "
    "the full delivery address, then confirm the order."
)
ORDER_TAKING_TE = "మేము ఆర్డర్ తీసుకోండి. డెలివరీ చిరునామా మరియు ఎంత కావాలో అడగండి."


def test_quote_only_brief_never_grants_order_confirmation():
    assert not order_confirmation_allowed_from_script(QUOTE_ONLY_EN)
    assert not order_confirmation_allowed_from_script(QUOTE_ONLY_TE)


def test_delivery_address_in_a_prohibition_does_not_authorize_course_orders():
    assert not order_confirmation_allowed_from_script(
        "Adult spoken-English course counselling. No need for delivery address, quantity, "
        "income or phone checklist. Save an enquiry only after consent."
    )


def test_do_not_take_orders_does_not_grant_an_order_workflow():
    assert not order_confirmation_allowed_from_script(
        "Do not take orders. Collect a delivery address for an enquiry only."
    )


def test_superseded_named_service_price_keeps_only_the_active_fact():
    from server.brain.fact_canon import canonicalize_superseded_facts

    for text in [
        "Old kitchen note 1299 is wrong; discard it, current kitchen fee 1599.",
        "Current kitchen fee is 1599; old kitchen note of 1299 is wrong and discarded.",
    ]:
        result = canonicalize_superseded_facts(text)
        assert "1299" not in result
        assert "1599" in result
        assert not result.lower().startswith("discard it")


def test_minimum_order_noun_alone_is_not_a_permission():
    _takes, proof_fields, prohibited = order_confirmation_evidence(QUOTE_ONLY_TE)
    assert proof_fields and prohibited


def test_order_taking_brief_grants_the_capability_fail_open_only_with_evidence():
    assert order_confirmation_allowed_from_script(ORDER_TAKING_EN)
    assert order_confirmation_allowed_from_script(ORDER_TAKING_TE)
    # The proof fields are what an actual order needs; a bare order verb is not enough.
    assert not order_confirmation_allowed_from_script("We take orders. Call us.")


def test_compiled_brain_carries_the_capability_and_refresh_recomputes_it():
    assembled = assemble_unified_brain(language="en-IN", script=ORDER_TAKING_EN)
    assert capabilities_section_present(assembled)
    assert order_confirmation_allowed(assembled)
    assert "order_confirmation: allowed" in assembled
    business = business_from_unified_brain(assembled)
    assert "delivery address" in business
    assert "CALL CAPABILITIES" not in business

    # A stored publication cannot keep a stale permission its script no longer supports.
    stale = assembled.replace("order_confirmation: allowed", "order_confirmation: not_allowed")
    assert order_confirmation_allowed(refresh_platform_sections(stale, "en-IN"))

    # Publications stored before the contract existed get it inserted on render.
    legacy = assembled.replace("--- CALL CAPABILITIES ---\norder_confirmation: allowed\n\n", "")
    assert "--- CALL CAPABILITIES ---" not in legacy
    refreshed = refresh_platform_sections(legacy, "en-IN")
    assert "order_confirmation: allowed" in refreshed


def test_compiled_quote_brief_section_denies_orders_even_in_telugu():
    assembled = assemble_unified_brain(language="te-IN", script=QUOTE_ONLY_TE)
    assert render_capabilities_section(QUOTE_ONLY_TE) == (
        "--- CALL CAPABILITIES ---\norder_confirmation: not_allowed"
    )
    assert not order_workflow_active(assembled)
    # Callers that pass a raw business script (no platform sections) still fail closed.
    assert not order_workflow_active(QUOTE_ONLY_TE)
    assert order_workflow_active(ORDER_TAKING_EN)
