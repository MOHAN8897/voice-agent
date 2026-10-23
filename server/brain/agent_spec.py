"""
AgentSpec and Deterministic Verifier — server/brain/agent_spec.py
Architecture: Brief -> AgentSpec (validated) -> Script
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from pydantic import BaseModel, Field, field_validator


class Evidenced(BaseModel):
    value: str | None = None
    evidence: str | None = None  # Exact quote from the brief that supports it
    confidence: float = 0.0      # 0.0 to 1.0


class WorkflowRequirement(BaseModel):
    """A source-backed obligation, kept separate from optional role defaults."""
    requirement_id: str
    kind: str
    text: str
    evidence: str
    condition: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True


class AgentSpec(BaseModel):
    agent_name: Evidenced = Field(default_factory=Evidenced)
    company_name: Evidenced = Field(default_factory=Evidenced)
    location: Evidenced = Field(default_factory=Evidenced)
    offering: Evidenced = Field(default_factory=Evidenced)
    call_objective: Evidenced = Field(default_factory=Evidenced)
    qualification_questions: list[str] = Field(default_factory=list)
    language_code: str  # Mandatory: No default allowed. Must come from request or tenant settings.
    tone: str | None = None
    constraints: list[str] = Field(default_factory=list)
    needs_user_input: list[str] = Field(default_factory=list)
    extraction_source: str = "llm"  # "llm_gemini" | "llm_openai" | "regex_fallback"
    raw_brief: str = ""
    spec_version: str = "v1"
    workflow: list[WorkflowRequirement] = Field(default_factory=list)
    opening_line: Evidenced = Field(default_factory=Evidenced)
    direction: str = "outbound"
    role: str = "other"
    generation_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("language_code")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        code = (v or "").strip()
        if not code:
            raise ValueError("language_code must be explicitly provided; no implicit default is allowed.")
        return code

    def spec_hash(self) -> str:
        """Deterministic fingerprint of validated spec."""
        payload = {
            "agent_name": self.agent_name.value,
            "company_name": self.company_name.value,
            "location": self.location.value,
            "offering": self.offering.value,
            "call_objective": self.call_objective.value,
            "qualification_questions": sorted(self.qualification_questions),
            "language_code": self.language_code,
            "tone": self.tone,
            "constraints": sorted(self.constraints),
            "spec_version": self.spec_version,
            "workflow": [item.model_dump() for item in self.workflow],
            "opening_line": self.opening_line.value,
            "direction": self.direction,
            "role": self.role,
            "generation_config": self.generation_config,
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


_LEGAL_SUFFIXES_REGEX = re.compile(
    r"\b(pvt\.?\s*ltd\.?|private\s+limited|ltd\.?|llp|llc|inc\.?|corp\.?|corporation|co\.?|company\s+limited)\b",
    re.I,
)

_CLAUSE_WORDS_REGEX = re.compile(
    r"\b(and\s+the\s+person|and\s+the\s+agent|and\s+the\s+caller|who\s+calls|who|calls?|calling|is|am|are|was|were|representing|telecaller|caller|executive|customer|user)\b",
    re.I,
)

_FORBIDDEN_DEFAULT_NAMES = {"priya", "alex"}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_substring_grounded(evidence: str, brief: str) -> bool:
    if not evidence or not brief:
        return False
    norm_ev = normalize_whitespace(evidence).lower()
    norm_br = normalize_whitespace(brief).lower()
    return norm_ev in norm_br


def _token_overlap_ratio(value: str, source: str) -> float:
    if not value or not source:
        return 0.0
    val_tokens = set(re.findall(r"\w+", value.lower()))
    if not val_tokens:
        return 0.0
    src_tokens = set(re.findall(r"\w+", source.lower()))
    overlap = val_tokens.intersection(src_tokens)
    return len(overlap) / len(val_tokens)


def _titlecase_name(name: str) -> str:
    tokens = normalize_whitespace(name).split()
    out = []
    for t in tokens:
        tl = t.lower()
        if tl in {"llp", "llc"}:
            out.append(t.upper())
        elif tl == "ltd" or tl == "ltd.":
            out.append("Ltd." if "." in t else "Ltd")
        elif tl == "pvt" or tl == "pvt.":
            out.append("Pvt." if "." in t else "Pvt")
        elif tl in {"and", "&", "of", "the"}:
            out.append(tl)
        elif any(c.isupper() for c in t[1:]):
            # Preserve camelCase / PascalCase like SunPower, FedEx, McDonald
            out.append(t)
        else:
            out.append(t.capitalize())
    return " ".join(out)


def verify_agent_spec(
    spec: AgentSpec,
    raw_brief: str,
    *,
    tenant_default_agent_name: str | None = None,
) -> AgentSpec:
    """
    Deterministic Grounding & Integrity Checks:
    1. Evidence must be grounded in raw brief.
    2. Value tokens must overlap with evidence or brief.
    3. Names cannot contain clause words.
    4. Company names stop at legal entity suffix if a suffix is present.
    5. Company names with 'and' (e.g. 'Mohan and Sons') are preserved, while clause spillover is clipped.
    6. Agent name cannot equal company name or default denylist names.
    7. Location cannot bleed into company name.
    8. Populate needs_user_input for mandatory missing fields.
    """
    norm_brief = normalize_whitespace(raw_brief)
    needs_input = list(spec.needs_user_input)

    # 1. Verify Grounding of Evidenced Fields
    for field_name in ["agent_name", "company_name", "location", "offering", "call_objective"]:
        ev_item: Evidenced = getattr(spec, field_name)
        if ev_item.value:
            if ev_item.evidence:
                if not _is_substring_grounded(ev_item.evidence, norm_brief):
                    # Evidence hallucination detected
                    ev_item.confidence = 0.0
                    ev_item.value = None
                    ev_item.evidence = None
                else:
                    overlap = _token_overlap_ratio(ev_item.value, ev_item.evidence)
                    if overlap < 0.5:
                        # Value not supported by evidence
                        ev_item.confidence = 0.0
                        ev_item.value = None
            else:
                overlap = _token_overlap_ratio(ev_item.value, norm_brief)
                if overlap < 0.5:
                    ev_item.confidence = 0.0
                    ev_item.value = None

    # 2. Company Name Verification & Suffix Clipping
    if spec.company_name.value:
        comp = normalize_whitespace(spec.company_name.value)
        # Check if legal suffix is present
        suffix_match = _LEGAL_SUFFIXES_REGEX.search(comp)
        if suffix_match:
            # Cut at the end of the legal suffix (e.g. "Mohan Private Limited and the person" -> "Mohan Private Limited")
            comp = comp[: suffix_match.end()].strip()

        # Reject if company has dangling clause words
        if _CLAUSE_WORDS_REGEX.search(comp):
            # Clip before clause words
            comp = _CLAUSE_WORDS_REGEX.split(comp)[0].strip()

        # Word count sanity
        words = comp.split()
        if len(words) > 8 or len(comp) < 2:
            spec.company_name.value = None
            spec.company_name.confidence = 0.0
        else:
            spec.company_name.value = _titlecase_name(comp)

    # 3. Agent Name Verification
    if spec.agent_name.value:
        name = normalize_whitespace(spec.agent_name.value)
        if _CLAUSE_WORDS_REGEX.search(name) or len(name.split()) > 6 or len(name) < 2:
            spec.agent_name.value = None
            spec.agent_name.confidence = 0.0
        elif name.lower() in _FORBIDDEN_DEFAULT_NAMES and not _is_substring_grounded(name, norm_brief):
            # Denylist old default names unless explicitly typed by the user in the brief
            spec.agent_name.value = None
            spec.agent_name.confidence = 0.0
        else:
            spec.agent_name.value = _titlecase_name(name)

    # 4. Cross-Field Sanity
    if spec.company_name.value and spec.agent_name.value:
        if spec.agent_name.value.lower() == spec.company_name.value.lower():
            spec.agent_name.value = None
            spec.agent_name.confidence = 0.0

    # 5. Location Leakage Check & Normalization
    if spec.location.value:
        spec.location.value = _titlecase_name(normalize_whitespace(spec.location.value))
        if spec.company_name.value:
            loc_words = set(re.findall(r"\w+", spec.location.value.lower()))
            comp_words = set(re.findall(r"\w+", spec.company_name.value.lower()))
            # If company name consists only of location words, reject company name
            if comp_words.issubset(loc_words):
                spec.company_name.value = None
                spec.company_name.confidence = 0.0

    # 6. Apply Missing-Field Policy
    if not spec.company_name.value:
        if "company_name" not in needs_input:
            needs_input.append("company_name")

    if not spec.offering.value and not spec.call_objective.value:
        if "offering_or_objective" not in needs_input:
            needs_input.append("offering_or_objective")

    if not spec.agent_name.value:
        if tenant_default_agent_name and tenant_default_agent_name.strip():
            spec.agent_name.value = _titlecase_name(tenant_default_agent_name.strip())
            spec.agent_name.confidence = 0.6
            spec.agent_name.evidence = "tenant_default"
        else:
            if "agent_name" not in needs_input:
                needs_input.append("agent_name")

    # Sanitize lists (remove empty/whitespace-only items)
    spec.qualification_questions = [
        normalize_whitespace(q) for q in spec.qualification_questions if normalize_whitespace(q)
    ]
    spec.constraints = [
        normalize_whitespace(c) for c in spec.constraints if normalize_whitespace(c)
    ]
    spec.needs_user_input = sorted(list(set(needs_input)))
    return spec
