"""Ground generation decisions in the brief before rendering any live instructions."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from server.brain.agent_spec import WorkflowRequirement


def brief_issue(code: str, message: str, *, field: str = "brief", evidence: str = "",
                severity: str = "error") -> dict[str, Any]:
    return {"code": code, "message": message, "description": message,
            "field": field, "evidence": evidence, "severity": severity}


class BriefValidationError(ValueError):
    def __init__(self, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__(" ".join(str(item["message"]) for item in issues))

    def to_dict(self) -> dict[str, Any]:
        return {"code": "brief_needs_clarification", "status": "needs_user_input",
                "message": str(self), "issues": self.issues,
                "needs_user_input": [item["message"] for item in self.issues]}


def source_supported(value: str, source: str) -> bool:
    """Require a whole source phrase outside a contradictory negative context."""
    def normalize(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

    proposed, original = normalize(value), normalize(source)
    if not proposed:
        return False
    for match in re.finditer(r"(?<!\w)" + re.escape(proposed) + r"(?!\w)", original):
        prior_clause = re.split(r"[.!?;।\n]", original[:match.start()])[-1]
        if not re.search(r"\b(?:never|not|no|don'?t|do not|without)\b", prior_clause):
            return True
        if re.match(r"^(?:never|not|no|don'?t|do not|without)\b", proposed):
            return True
    return False


def normalize_generation_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise BriefValidationError([brief_issue("invalid_configuration", "Generation settings must be an object.")])
    result: dict[str, Any] = {}
    for key in ("employeeName", "agentRole", "callDirection", "mode", "industry"):
        value = config.get(key)
        if value is not None and str(value).strip():
            if not isinstance(value, str) or len(value) > 120 or "\n" in value:
                raise BriefValidationError([brief_issue("invalid_configuration", f"Invalid {key} setting.", field=key)])
            result[key] = value.strip()
    if "naturalSpokenStyle" in config:
        if not isinstance(config["naturalSpokenStyle"], bool):
            raise BriefValidationError([brief_issue("invalid_configuration", "Natural spoken style must be true or false.", field="naturalSpokenStyle")])
        result["naturalSpokenStyle"] = config["naturalSpokenStyle"]
    if result.get("mode") and result["mode"] not in {"instant_lead", "bulk"}:
        raise BriefValidationError([brief_issue("invalid_mode", "Choose a supported call mode.", field="mode")])
    if result.get("industry") and not re.fullmatch(r"[a-z][a-z0-9_-]{0,119}", result["industry"]):
        raise BriefValidationError([brief_issue("invalid_industry", "Choose an industry label; describe custom details in the brief.", field="industry")])
    if result.get("callDirection"):
        direction = result["callDirection"].lower()
        if direction not in {"inbound", "outbound", "incoming", "outgoing", "in", "out"}:
            raise BriefValidationError([brief_issue("invalid_direction", "Choose inbound or outbound calls.", field="callDirection")])
        result["callDirection"] = "inbound" if direction in {"inbound", "incoming", "in"} else "outbound"
    return result


def _negative_or_quoted(text: str, start: int) -> bool:
    prefix = re.split(r"[.!?;\n।]", text[:start])[-1]
    return bool(re.search(r"\b(?:never|do not|don't|must not|avoid|refuse|reject|forbid)\b", prefix, re.I)
                or re.search(r"\b(?:if|when)\b.*\b(?:says?|asks?|requests?|hears?)\b", prefix, re.I))


def validate_brief_requirements(brief: str, *, language: str) -> list[dict[str, Any]]:
    """Conservative hard checks; arbitrary semantic correctness is not claimed."""
    issues: list[dict[str, Any]] = []
    if sum(char.isalpha() for char in brief) < 3:
        return [brief_issue("missing_brief", "Describe who the agent represents and what the call should accomplish.")]
    injection = re.compile(
        r"\b(?:ignore|override|disregard)\s+(?:(?:all|the|your)\s+)?(?:previous\s+)?(?:system|platform|safety|developer)?\s*(?:instructions?|rules?|prompts?)"
        r"|\b(?:reveal|print|show|disclose)\b[^.\n]{0,45}\b(?:system|hidden|developer)\s+(?:prompts?|instructions?)", re.I)
    for match in injection.finditer(brief):
        if not _negative_or_quoted(brief, match.start()):
            issues.append(brief_issue("platform_override", "Remove instructions to override platform rules or disclose hidden prompts.", evidence=match.group(0)))
    forged = re.search(r"(?im)^\s*(?:---\s*(?:CORE SAFETY|SYSTEM(?: PROMPT)?|STATIC OUTPUT RULES|PLATFORM CALL RULES|LANGUAGE LOCK|RUNTIME FOOTER)\s*---|<\s*/?\s*(?:system|developer)\s*>)", brief)
    if forged:
        issues.append(brief_issue("reserved_heading", "Platform instruction headings cannot be supplied in a business brief.", evidence=forged.group(0).strip()))
    secrets = re.compile(r"\b(?:collect|request|ask(?:\s+(?:them|the\s+callers?|callers?|users?|customers?))?\s+for|obtain|capture)\b[^.\n;]{0,70}\b(?:otp|one[- ]time password|pin|cvv|password|full\s+(?:credit\s+|debit\s+|bank\s+)?card\s+number)\b", re.I)
    for match in secrets.finditer(brief):
        if not _negative_or_quoted(brief, match.start()):
            issues.append(brief_issue("sensitive_collection", "The agent cannot collect OTPs, PINs, passwords, CVV or full card numbers; use an approved secure flow.", evidence=match.group(0)))
    language_names = {"english": "en", "telugu": "te", "hindi": "hi", "tamil": "ta", "kannada": "kn",
                      "malayalam": "ml", "marathi": "mr", "bengali": "bn", "gujarati": "gu", "punjabi": "pa"}
    locale_pattern = r"\b(?:speak|respond|talk|communicate)\s+(?:in\s+)?(?:only|exclusively)\s+(?:in\s+)?(" + "|".join(language_names) + r")\b"
    for match in re.finditer(locale_pattern, brief, re.I):
        if not _negative_or_quoted(brief, match.start()) and language_names[match.group(1).lower()] != language.split("-")[0]:
            issues.append(brief_issue("language_conflict", "The brief's exclusive spoken language conflicts with the selected language. Choose one primary language.", field="language", evidence=match.group(0)))
    only_prices = list(re.finditer(r"\b(?:only|single|fixed)\s+(?:price|fee)\s*(?:is|:|=)?\s*((?:INR|USD|GBP|Rs\.?|₹|\$|£)\s*[\d,]+(?:\.\d+)?)", brief, re.I))
    values = {re.sub(r"[\s,]", "", match.group(1)).casefold() for match in only_prices}
    if len(values) > 1:
        issues.append(brief_issue("price_conflict", "More than one exclusive price is specified. Identify the current price or distinguish the products and units.", field="price", evidence="; ".join(match.group(0) for match in only_prices)))
    return issues


_NAME_WORD = r"(?:[^\W\d_]|[\u0300-\u036f\u0900-\u0dff])(?:[^\W_]|[\u0300-\u036f\u0900-\u0dff'’\-])*"
_NAME_VALUE = rf"({_NAME_WORD}(?:\s+{_NAME_WORD}){{0,3}})"
_NAME_STOPS = re.compile(
    r"\s+(?:from|for|who|whose|that|and|at|about|should|must|will|can|representing|working|work|with|to|is|also|people|calls?|calling|call\s+her|call\s+him|"
    r"i|we|you|u|wants?|needs?|just|related|realted|regarding|of|company|business|firm|agency|agencies|clinic|hospital|store|shop|"
    r"selling|sells|sell|buying|buys|buy|booking|books|book|है|और|से|का|की|के|మరియు|నుండి|కోసం|అనే|ఆమె|అతను)(?:\b|\s|[.,;।!?]|$)",
    re.I,
)


def clean_person_name(value: str) -> str:
    value = _NAME_STOPS.split(value.strip(" \t\"'“”.,;:।"), maxsplit=1)[0]
    words = value.split()
    if not 0 < len(words) <= 4 or len(value) > 60:
        return ""
    if any(not (unicodedata.category(char)[0] in {"L", "M"} or char in " '’-") for char in value):
        return ""
    stop_words = {
        "agent", "named", "naed", "name", "is", "the", "person", "representative", "bot",
        "assistant", "company", "business", "i", "we", "you", "u", "never", "not", "no",
        "ask", "asking", "call", "calls", "calling", "verify", "check", "confirm", "help",
        "for", "should", "speak", "from", "about",
        "please", "do", "don't", "dont", "private", "limited", "ltd", "llp", "llc",
    }
    if any(word.casefold() in stop_words for word in words):
        return ""
    return " ".join(word[:1].upper() + word[1:] if word.islower() else word for word in words)


def identity_candidates(brief: str) -> list[dict[str, Any]]:
    patterns: tuple[tuple[int, str], ...] = (
        (100, rf"\bcreate\s+(?:an?\s+)?(?:\w+\s+){{0,4}}agent\s+(?:named|naed|name\b\s*(?:is|:|=)?)\s*{_NAME_VALUE}"),
        (95, rf"\b(?:actual|correct|new)\s+(?:agent\s+)?name\b\s*(?:is|:|=)?\s*{_NAME_VALUE}"),
        (92, rf"\bagnet\s+name\s*(?:is|:|=)?\s*{_NAME_VALUE}"),
        (90, rf"\b(?:it[\'’]?s|his|her|agent[\'’]?s|their|the)\s+name\s*(?:is|:|=)?\s*{_NAME_VALUE}"),
        (90, rf"\bagent\s+(?:named|naed|name\b\s*(?:is|:|=)?|is)\s*{_NAME_VALUE}"),
        (90, rf"\b(?:counsel(?:l)?or|consultant|salesperson|receptionist|advisor)\s+named\s+{_NAME_VALUE}"),
        (88, rf"\bname\s*(?:is|:|=)\s*{_NAME_VALUE}"),
        (88, rf"\bagent\s*[:=]\s*{_NAME_VALUE}"),
        (85, rf"\bnamed\s+{_NAME_VALUE}"),
        (85, rf"\bcall\s+(?:him|her|it|them|the\s+agent)\s+{_NAME_VALUE}"),
        (85, rf"\b(?:person|representative)\s+(?:who\s+calls(?:\s+the\s+users)?\s+is|named|naed)\s+{_NAME_VALUE}"),
        (70, rf"\bagent\s+{_NAME_VALUE}(?=\s*(?:[,.;]|from\b|for\b|at\b|company\b))"),
        (65, rf"\bsomeone\s+like\s+{_NAME_VALUE}(?=\s+who\s+will\s+call\b)"),
        (60, rf"^\s*([A-Z][a-z]+)\s+for\s+[A-Z]"),
        (80, rf"(?:एजेंट|एजेन्ट|प्रतिनिधि)(?:\s+का)?\s+नाम(?:\s+है)?\s*[:=]?\s*{_NAME_VALUE}"),
        (80, rf"(?:ఏజెంట్|ప్రతినిధి|మీ)(?:\s+యొక్క)?\s+పేరు\s*[:=]?\s*{_NAME_VALUE}"),
        (50, rf"\b(?:you are|I am|I'm)\s+{_NAME_VALUE}"),
        (20, rf"\bmy\s+name\s+is\s+{_NAME_VALUE}"),
    )
    candidates: list[dict[str, Any]] = []
    for priority, pattern in patterns:
        for match in re.finditer(pattern, brief, re.I):
            # A bare 'name is' / 'named' can describe the customer or business.
            # It must not outrank an explicit person-who-calls clause.
            if priority in {85, 88} and re.search(
                r"\b(?:customer|caller|client|callee|contact|patient|student|company|business|agency|firm|product|brand)\s*$",
                brief[:match.start()], re.I,
            ):
                continue
            name = clean_person_name(match.group(1))
            if not name:
                continue
            prefix = re.split(r"[.!?;\n।]", brief[:match.start()])[-1]
            negative = bool(re.search(r"\b(?:not|never|don't|do not|avoid|instead of)\b", prefix, re.I))
            correction = bool(re.search(r"\b(?:actual|correct|correction|actually|instead|rename|change)\b", prefix + " " + match.group(0)[:match.start(1)-match.start()], re.I))
            candidates.append({"value": name, "evidence": match.group(0), "start": match.start(),
                               "end": match.end(), "negative": negative, "correction": correction,
                               "priority": priority})
    return sorted(candidates, key=lambda item: (-item.get("priority", 0), item["start"]))


def resolve_agent_identity(brief: str, *, fallback: str = "", interpreted: str = "",
                           explicit: str = "", allow_default: bool = False,
                           default_name: str = "Priya") -> tuple[str, list[dict[str, Any]], str]:
    candidates = identity_candidates(brief)
    positives = [item for item in candidates if not item["negative"]]
    corrections = [item for item in positives if item["correction"]]
    if corrections:
        positives = [item for item in positives if item["start"] >= corrections[-1]["start"]]
    values = {item["value"].casefold(): item["value"] for item in positives}
    selected = clean_person_name(explicit) if explicit else ""
    if explicit and not selected:
        return "", [brief_issue("invalid_agent_name", "Supply a valid spoken agent name.", field="employeeName")], ""
    if selected and positives and selected.casefold() not in values:
        return "", [brief_issue("identity_conflict", "The selected speaker name conflicts with the brief. Make both names agree.", field="employeeName", evidence="; ".join(item["evidence"] for item in positives))], ""
    if not selected and len(values) > 1:
        top_priority = max(item["priority"] for item in positives)
        top_values = {item["value"].casefold(): item["value"] for item in positives if item["priority"] == top_priority}
        if len(top_values) > 1:
            return "", [brief_issue("identity_conflict", "Different agent names are specified. State the one current speaker name.", field="agent_name", evidence="; ".join(item["evidence"] for item in positives if item["priority"] == top_priority))], ""
        values = top_values
    if not selected and values:
        selected = next(iter(values.values()))
    negative_names = {item["value"].casefold() for item in candidates if item["negative"]}
    if not selected and interpreted:
        normalized = clean_person_name(interpreted)
        if normalized and source_supported(normalized, brief) and normalized.casefold() not in negative_names:
            selected = normalized
    if not selected and fallback:
        normalized = clean_person_name(fallback)
        if normalized and (allow_default or source_supported(normalized, brief)) and normalized.casefold() not in negative_names:
            selected = normalized
    if not selected and allow_default:
        normalized = clean_person_name(default_name)
        if normalized and normalized.casefold() not in negative_names:
            selected = normalized
    if not selected:
        return "", [brief_issue("missing_agent_name", "What name should the agent use when speaking?", field="agent_name")], ""
    evidence = next((item["evidence"] for item in positives if item["value"].casefold() == selected.casefold()), selected if (explicit or allow_default) else selected)
    return selected, [], evidence


def extract_exact_opening(brief: str) -> str:
    match = re.search(r"\b(?:(?:exact|approved|custom)\s+(?:opening|greeting)(?:\s+(?:line|text))?|(?:open|start)\s+(?:exactly\s+)?with)\s*(?:is|:|=)?\s*[\"“']([^\"”'\n]+)[\"”']", brief, re.I)
    return match.group(1).strip() if match else ""


# Phone TTS speaks about 15 characters a second in every supported script
# (call 35002575: a 251-character Telugu opening took 16.5 s). Past ~8 s the
# callee talks over the opening or hangs up before the agent asks anything.
OPENING_CHARS_PER_SECOND = 15.0
OPENING_MAX_SECONDS = 8.0


def estimate_speech_seconds(text: str) -> float:
    return round(len(" ".join((text or "").split())) / OPENING_CHARS_PER_SECOND, 1)


def opening_length_issue(opening: str, *, field: str = "opening") -> dict[str, Any] | None:
    """Warn, never trim: the tenant's opening is spoken as written."""
    seconds = estimate_speech_seconds(opening)
    if seconds <= OPENING_MAX_SECONDS:
        return None
    return brief_issue(
        "opening_too_long",
        f"The opening line takes about {seconds:.0f} seconds to say. Openings over "
        f"{OPENING_MAX_SECONDS:.0f} seconds are often interrupted; consider a shorter greeting.",
        field=field, evidence=opening.strip()[:280], severity="warning",
    )


def _requirement_key(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def workflow_requirements(brief: str, interpreted: dict[str, Any] | None = None) -> list[WorkflowRequirement]:
    requirements: list[WorkflowRequirement] = []
    # A line break inside a sentence is just wrapping; only blank lines, list items and
    # sentence punctuation end a requirement. ';' stays inside: "Fridge inspection costs
    # 250 rupees; the charge is waived if..." must keep the product it applies to.
    joined = re.sub(r"(?<![.!?।:\n])\n(?!\s*(?:[-*•]|\d+[.)])\s)(?=\S)", " ", brief)
    sentences = [part.strip(" -*•") for part in re.split(r"(?<=[.!?।])\s+|\n+", joined) if part.strip(" -*•")]
    for text in sentences:
        agent_creation_match = re.search(
            rf"\b(?:create\s+(?:an?\s+)?(?:\w+\s+){{0,4}}agent\s+(?:named|naed|name\b\s*(?:is|:|=)?)|agent\s+(?:named|naed))\s+{_NAME_WORD}",
            text,
            re.I,
        )
        if agent_creation_match:
            clean_target = text[agent_creation_match.end():].strip(" ,;:-")
        else:
            clean_target = re.sub(
                r"^(?:ok\s+|so\s+)?(?:u|you)\s+are\s+(?:an?\s+)?(?:\w+\s+){0,6}(?:named|person\s+named)\s+\w+\s*",
                "",
                text,
                flags=re.I,
            )
            clean_target = re.sub(
                r"^create\s+(?:an?\s+)?(?:\w+\s+){0,4}agent\s+na?m?e?d\s+\w+\s*",
                "",
                clean_target,
                flags=re.I,
            )
            clean_target = re.sub(r"^(?:whose\s+work\s+is\s+(?:doing\s+)?|whose\s+job\s+is\s+|work\s+is\s+)", "", clean_target, flags=re.I).strip()
        clean_target = re.sub(r"\bcalsl\b", "calls", clean_target, flags=re.I)
        clean_target = re.sub(r"\binsturance\b", "insurance", clean_target, flags=re.I)
        clean_target = re.sub(r"\brealted\b", "related", clean_target, flags=re.I)
        clean_target = re.sub(r"\beveything\b", "everything", clean_target, flags=re.I)
        clean_target = re.sub(r"\bwho\s+should\s+convince\s+(?:the\s+)?users?\s+to\b", "help callers to", clean_target, flags=re.I)
        clean_target = re.sub(r"\bwho\s+should\s+convince\b", "help callers", clean_target, flags=re.I)
        target = clean_target if clean_target else text
        if re.search(r"\b(?:never|do not|don't|no\s+\w+|must not|only|strictly|prohibit\w*|forbid\w*)\b", target, re.I):
            kind = "constraint"
        elif re.search(r"\b(?:if|when|unless|otherwise|before|after|until)\b", target, re.I):
            kind = "branch"
        elif re.search(r"\b(?:ask|confirm|verify|check|explain|offer|collect|help|goal|objective|book|schedule|tell|provide|answer)\b", target, re.I):
            kind = "objective"
        else:
            continue
        condition = None
        match = re.match(r"((?:if|when|unless|before|after|until)\b[^,;]+)[,;]", target, re.I)
        if match:
            condition = match.group(1)
        requirements.append(WorkflowRequirement(requirement_id=f"R{len(requirements)+1}", kind=kind,
            text=target, evidence=text, condition=condition, required=not bool(re.search(r"\b(?:optional|may optionally)\b", target, re.I))))
    for item in (interpreted or {}).get("requirements", []):
        if not isinstance(item, dict):
            continue
        evidence, text = str(item.get("evidence") or ""), str(item.get("text") or "")
        # A paraphrase is never the sole record of an operational instruction.
        if source_supported(evidence, brief) and text and source_supported(text, evidence):
            key = _requirement_key(evidence)
            if not any(key in _requirement_key(existing.evidence) or _requirement_key(existing.evidence) in key
                       for existing in requirements):
                requirements.append(WorkflowRequirement(requirement_id=f"R{len(requirements)+1}",
                    kind=str(item.get("kind") or "objective"), text=evidence, evidence=evidence,
                    condition=str(item.get("condition") or "") or None))
    return requirements


def render_workflow(requirements: list[WorkflowRequirement]) -> str:
    if not requirements:
        return ""
    lines = ["--- BUSINESS WORKFLOW ---", "Follow the applicable source requirements below. Conditions are alternatives, not a checklist.",
             "Complete prerequisites before dependent actions. Ask at most one useful unanswered question per turn.",
             "Explicit prohibitions override optional role suggestions. Skip answered and inapplicable steps.",
             "A requested action is complete only after its required tool returns success; otherwise explain the limitation."]
    for item in requirements:
        lines.append(f"- {item.requirement_id} [{item.kind}; {'required' if item.required else 'optional'}]: {item.text}")
    return "\n".join(lines)
