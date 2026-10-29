"""Corroborate optional CRM identity fields before an authorized create."""
from __future__ import annotations

from typing import Any

from server.call.memory_manager import memory_manager


def ground_contact_fields(ctx: Any, arguments: dict) -> dict:
    facts = dict((memory_manager.peek_snapshot(str(getattr(ctx, "call_id", ""))) or {}).get("facts") or {})
    for operation in (getattr(ctx, "turn_control", None) or {}).get("memory_operations", []):
        if operation.get("op") in {"set_fact", "set_preference"}:
            facts[operation.get("key")] = operation.get("value")
    result = dict(arguments)
    full_name = " ".join(str(facts.get(k) or "") for k in ("caller_name", "contact_name", "customer_name")).casefold()
    for field in ("firstname", "lastname"):
        value = str(result.get(field) or "").strip()
        if value and ("@" in value or value.casefold() not in full_name):
            if "@" in value and not result.get("email"):
                result["email"] = value
            result.pop(field, None)
    company = str(result.get("company") or "").strip()
    if company and company.casefold() not in {str(facts.get(k) or "").casefold() for k in ("company", "employer", "organization")}:
        result.pop("company", None)
    return result
