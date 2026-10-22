"""
Semantic validation for business brain sections — prd/12 §27.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from server.brain.sections import SECTION_MAX_CHARS, SECTION_REQUIRED_TYPES, SECTION_TYPES


@dataclass
class ValidationIssue:
    severity: str  # blocking | warning
    code: str
    message: str
    section_ids: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "section_ids": i.section_ids,
                }
                for i in self.issues
            ],
        }


def _malformed_variables(text: str) -> bool:
    # Fallback values may contain normal punctuation, but never nested braces.
    without_tags = re.sub(r"\{\{\s*[A-Za-z_][\w.]*\s*(?:\|[^{}]*)?\}\}", "", text)
    return "{{" in without_tags or "}}" in without_tags


def validate_sections(sections: list[dict[str, Any]]) -> ValidationResult:
    issues: list[ValidationIssue] = []
    by_type: dict[str, list[dict]] = {}
    for s in sections:
        stype = s.get("type", "")
        if stype not in SECTION_TYPES:
            issues.append(
                ValidationIssue("blocking", "invalid_type", f"Unknown section type: {stype}", [str(s.get("section_id", ""))])
            )
            continue
        by_type.setdefault(stype, []).append(s)
        raw = str(s.get("raw_text") or "")
        if len(raw) > SECTION_MAX_CHARS:
            issues.append(
                ValidationIssue(
                    "blocking",
                    "section_too_long",
                    f"Section '{s.get('title')}' exceeds {SECTION_MAX_CHARS} characters",
                    [str(s.get("section_id", ""))],
                )
            )
        if s.get("enabled") and not raw.strip() and stype in SECTION_REQUIRED_TYPES:
            issues.append(
                ValidationIssue(
                    "blocking",
                    "required_empty",
                    f"Required section '{stype}' cannot be empty when enabled",
                    [str(s.get("section_id", ""))],
                )
            )
        if s.get("enabled", True) and _malformed_variables(raw):
            issues.append(
                ValidationIssue(
                    "blocking",
                    "malformed_variable",
                    "A variable tag is malformed. Use {{variable}} or {{variable | fallback}}.",
                    [str(s.get("section_id", ""))],
                )
            )

    for req in SECTION_REQUIRED_TYPES:
        enabled = [s for s in by_type.get(req, []) if s.get("enabled")]
        if not enabled:
            issues.append(ValidationIssue("blocking", "missing_required", f"Missing enabled section: {req}"))

    # Cross-section conflict heuristic: contradictory refund windows
    refund_mentions: list[tuple[str, str]] = []
    for s in sections:
        if not s.get("enabled", True):
            continue
        raw = str(s.get("raw_text") or "").lower()
        if "refund" in raw or "return" in raw:
            refund_mentions.append((str(s.get("section_id")), raw))
    if len(refund_mentions) >= 2:
        windows = set()
        for _, raw in refund_mentions:
            m = re.search(r"(\d+)\s*(day|days)", raw)
            if m:
                windows.add(m.group(0))
        if len(windows) > 1:
            issues.append(
                ValidationIssue(
                    "warning",
                    "conflicting_refund_policy",
                    f"Possible conflicting refund windows: {sorted(windows)}. Check whether they describe different products or policies.",
                    [sid for sid, _ in refund_mentions],
                )
            )

    blocking = [i for i in issues if i.severity == "blocking"]
    return ValidationResult(ok=not blocking, issues=issues)
