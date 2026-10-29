"""Compiled capability contract — permissions come from typed evidence, not prose.

The audit (F10) found that a Telugu quote-only brief offered order confirmation
because its minimum-order sentence contains the noun "ఆర్డర్". Scanning the whole
compiled prompt for an order noun cannot distinguish "take orders" from "we
cannot confirm an order", so the compiler now derives a small explicit section
from the business script and every runtime consumer reads only that section:

    --- CALL CAPABILITIES ---
    order_confirmation: not_allowed

Classification is fail-closed: a positive order-taking signal, the fields a real
order needs, and the absence of a global order prohibition must all hold. The
section is recomputed at render time, so a stored publication cannot keep a
permission its script no longer supports.
"""
from __future__ import annotations

import re

CAPABILITIES_HEADER = "--- CALL CAPABILITIES ---"
_CAPABILITIES_HEADER_RE = re.compile(r"(?m)^---\s*CALL CAPABILITIES\s*---[ \t]*$")
_ORDER_CAP_LINE = re.compile(r"(?m)^order_confirmation:\s*(allowed|not_allowed)\s*$")
_BUSINESS_END = re.compile(
    r"(?m)^--- (?:CALL CAPABILITIES|PLATFORM CALL RULES|CALL END POLICY|STATIC OUTPUT RULES) ---"
)

# Positive order-taking evidence. English phrases name the act explicitly; the
# Indic forms are imperatives/infinitives for taking an order, not the generic
# "ఆర్డర్ చేయాలి" (must order) that a minimum-order condition uses.
_ORDER_TAKING = re.compile(
    r"\b(?:take|taking|accept|accepting|place|placing|record|recording|handle|process)"
    r"\b[^.\n]{0,40}\borders?\b|"
    r"\b(?:order|purchase)\b[^.\n]{0,40}\b(?:quantity|delivery address|shipping address)\b|"
    r"\bconfirm\s+(?:the\s+|an?\s+)?order\b|"
    r"ఆర్డర్\s*(?:తీసుకో|తీసుకోండి|పెట్టుకో)|"
    r"ऑर्डर\s*(?:ले|लें|लूँ|बुक कर)|"
    r"ஆர்டர்\s*(?:எடு|எடுங்கள்|பெறு)|"
    r"ಆರ್ಡರ್\s*(?:ತಗೊ|ತೆಗೆದುಕೊ)|"
    r"ഓർഡർ\s*(?:എടു|എടുക്ക)|"
    r"অর্ডার\s*(?:নিন|নেব|গ্রহণ)|"
    r"ઓર્ડર\s*(?:લો|લેલો|સ્વીકાર)|"
    r"ਆਰਡਰ\s*(?:ਲਓ|ਲੈ|ਲਵੋ)",
    re.I,
)

# A negative statement about confirming/claiming an order. Both word orders are
# present across the Indic scripts, so each direction is checked.
_ORDER_PROHIBITION = re.compile(
    r"\b(?:do not|don't|never|cannot|can't|can not|unable to|not able to|not permitted to|"
    r"must not|should not)\b[^.\n]{0,60}\b(?:confirm|claim|promise|guarantee|place|process|take|accept|record|handle)\b"
    r"[^.\n]{0,40}\b(?:orders?|purchases?)\b|"
    r"\b(?:orders?|purchases?)\b[^.\n]{0,40}\b(?:cannot|can't|can not|is not|are not|won't|will not)\b"
    r"[^.\n]{0,20}\b(?:be\s+)?(?:confirmed|placed|processed|claimed)\b|"
    r"(?:ఆర్డర్|ఆర్డరు)[^.\n]{0,40}(?:కన్ఫర్మ్|నిర్ధార|క్లెయిమ్)[^.\n]{0,20}(?:లేరు|లేదు|కాదు|వద్దు)|"
    r"(?:కన్ఫర్మ్|నిర్ధార|క్లెయిమ్)[^.\n]{0,40}(?:ఆర్డర్|ఆర్డరు)[^.\n]{0,20}(?:లేరు|లేదు|కాదు|వద్దు)|"
    r"ऑर्डर[^.\n]{0,40}(?:पुष्टि|कन्फर्म)[^.\n]{0,20}(?:नहीं|मत)|"
    r"(?:पुष्टि|कन्फर्म)[^.\n]{0,40}ऑर्डर[^.\n]{0,20}(?:नहीं|मत)|"
    r"ஆர்டர்[^.\n]{0,40}(?:உறுதி|கன்ஃபர்ம்)[^.\n]{0,20}(?:இல்லை|வேண்டாம்|முடியாது)|"
    r"ಆರ್ಡರ್[^.\n]{0,40}(?:ದೃಢೀಕರಿಸ|ಕನ್ಫರ್ಮ್)[^.\n]{0,20}(?:ಇಲ್ಲ|ಬೇಡ|ಸಾಧ್ಯವಿಲ್ಲ)|"
    r"ഓർഡർ[^.\n]{0,40}(?:സ്ഥിരീകര|കൺഫേം)[^.\n]{0,20}(?:ഇല്ല|വേണ്ട|കഴിയില്ല)|"
    r"অর্ডার[^.\n]{0,40}(?:নিশ্চিত|কনফার্ম)[^.\n]{0,20}(?:নয়|না|নেই)|"
    r"ઓર્ડર[^.\n]{0,40}(?:પુષ્ટિ|કન્ફર્મ)[^.\n]{0,20}(?:નથી|ના|નહીં)|"
    r"ਆਰਡਰ[^.\n]{0,40}(?:ਪੁਸ਼ਟੀ|ਕਨਫਰਮ)[^.\n]{0,20}(?:ਨਹੀਂ|ਨਾ)",
    re.I,
)

# The fields a confirmed order actually needs. A brief that never mentions any
# of them is describing a sale, quote or enquiry, not an order workflow.
_ORDER_PROOF_FIELDS = re.compile(
    r"\b(?:delivery address|shipping address|delivery|dispatch|shipment)\b|"
    r"(?:డెలివరీ|చిరునామా)|(?:डिलीवरी|पता)|(?:டெலிவரி|முகவரி)|"
    r"(?:ಡೆಲಿವರಿ|ವಿಳಾಸ)|(?:ഡെലിവറി|വിലാസം)|(?:ডেলিভারি|ঠিকানা)|"
    r"(?:ડિલિવરી|સરનામું)|(?:ਡਿਲਿਵਰੀ|ਪਤਾ)",
    re.I,
)


def business_text(compiled_text: str | None) -> str:
    """The authored business script, without platform-owned sections."""
    raw = (compiled_text or "").strip()
    start = re.search(r"(?m)^--- CALLING SCRIPT ---[ \t]*$", raw)
    if start:
        body = raw[start.end():]
        end = _BUSINESS_END.search(body)
        return (body[:end.start()] if end else body).strip()
    return raw


def order_confirmation_evidence(compiled_text: str | None) -> tuple[bool, bool, bool]:
    """(takes_orders, names_proof_fields, prohibits_confirmation) from the script."""
    business = business_text(compiled_text)
    return (
        bool(_ORDER_TAKING.search(business)),
        bool(_ORDER_PROOF_FIELDS.search(business)),
        bool(_ORDER_PROHIBITION.search(business)),
    )


def order_confirmation_allowed_from_script(compiled_text: str | None) -> bool:
    takes_orders, proof_fields, prohibited = order_confirmation_evidence(compiled_text)
    return takes_orders and proof_fields and not prohibited


def render_capabilities_section(compiled_text: str | None) -> str:
    allowed = order_confirmation_allowed_from_script(compiled_text)
    return (
        f"{CAPABILITIES_HEADER}\n"
        f"order_confirmation: {'allowed' if allowed else 'not_allowed'}"
    )


def apply_available_tools(text: str, tools: list[dict], *, followup_config: dict | None = None) -> str:
    """Replace platform permissions with this agent/session's executable actions."""
    names = {str(tool.get("name") or "").upper() for tool in tools}
    rows = [CAPABILITIES_HEADER, "capabilities_source: runtime_tools_v1",
            f"order_confirmation: {'allowed' if 'CONFIRM_ORDER' in names else 'not_allowed'}",
            "Business workflow steps are conditional on these actions. Collecting details is not completion; success requires a successful server result.",
            "CONFIRM_ORDER, when listed, records the order in this call's platform ledger; it does not prove payment, external fulfilment or an email was sent.",
            "A caller-requested callback can be saved by the platform after required details and timing are collected. It does not guarantee an automatically scheduled call.",
            "Record explicit requests to stop future calls as do_not_call, separately from ending this call. Ordinary refusal, abuse, questions or a goodbye do not by themselves opt out of future contact."]
    enabled = bool((followup_config or {}).get("enabled"))
    mode = str((followup_config or {}).get("callbackMode") or "review") if enabled else "manual_only"
    rows.extend([f"callback_dispatch: {mode}",
                 f"missed_call_dispatch: {(followup_config or {}).get('missedMode', 'off') if enabled else 'off'}",
                 "Collect the caller's desired callback time, including short answers to your timing question. Never turn a future-interest request into a rejection or permanent opt-out.",
                 "When the caller asks to be called back, acknowledge naturally that you are noting their callback request and time; the platform saves it as the call closes. Never say you cannot note or arrange a callback."])
    if mode == "automatic":
        rows.append("The tenant permits automatic callbacks after the server resolves timing and passes calling-window, DND and account checks. A saved request is not a confirmed call time; do not promise an exact dial or claim a schedule succeeded without a server result.")
    else:
        rows.append("The team must review callback requests. Do not promise that an automatic callback or exact appointment has been scheduled.")
    if not tools:
        rows.append("No in-call action tools are available. Answer questions without promising a submission, booking or order.")
    for tool in tools[:32]:
        name = str(tool.get("name") or "")
        required = (tool.get("parameters") or {}).get("required") or []
        rows.append(f"- {name}; required: {', '.join(required) or 'none'}")
    block = "\n".join(rows)
    pattern = re.compile(r"(?ms)^--- CALL CAPABILITIES ---[ \t]*\n.*?(?=^--- (?:PLATFORM CALL RULES|CALL END POLICY|STATIC OUTPUT RULES) ---|\Z)")
    if pattern.search(text):
        return pattern.sub(lambda _: block + "\n\n", text, count=1)
    return text.rstrip() + "\n\n" + block


async def agent_available_tools(agent_id: str, compiled_text: str, *, tenant_id: str | None = None) -> list[dict]:
    """Use the same tenant/agent permission filters as live action execution."""
    from server.brain.agent_service import agent_service
    from server.db.connection import get_session_factory
    from server.services.tenant_tool_cache import get_active_app_names
    from server.services.tool_schema_registry import get_tools_for_agent

    factory = get_session_factory()
    if not tenant_id:
        try:
            agent = await agent_service.get_agent(agent_id)
            tenant_id = agent.get("tenant_id")
        except (KeyError, ValueError):
            return []
    if not factory or not tenant_id:
        return []
    active = await get_active_app_names(str(tenant_id), factory)
    return (await get_tools_for_agent(active, str(tenant_id), agent_id, factory,
                                     include_platform=True, compiled_text=compiled_text))[:32]


async def compile_agent_capabilities(text: str, agent_id: str) -> str:
    from server.db.connection import get_session_factory
    from server.brain.agent_service import agent_service
    from server.db.models.followup_models import AgentFollowUpPolicy
    from sqlalchemy import select
    from sqlalchemy.exc import ProgrammingError, OperationalError
    import uuid

    factory = get_session_factory()
    if factory is None:
        return text
    agent = await agent_service.get_agent(agent_id)
    from server.brain.compiled_brain_artifact import refresh_platform_sections
    from server.prompts.agent_voice_rules import inject_recording_disclosure
    language = str((agent.get("languages") or ["en-IN"])[0])
    text = refresh_platform_sections(text, language)
    text = inject_recording_disclosure(text, enabled=bool(agent.get("recording_disclosure_enabled")),
                                      disclosure_text=agent.get("recording_disclosure_text"), language=language)
    tenant_id = agent.get("tenant_id")
    config = None
    if tenant_id:
        try:
            async with factory() as session:
                policy = await session.scalar(select(AgentFollowUpPolicy).where(
                    AgentFollowUpPolicy.tenant_id == uuid.UUID(str(tenant_id)),
                    AgentFollowUpPolicy.agent_id == uuid.UUID(agent_id)))
                config = policy.config if policy else None
        except (ProgrammingError, OperationalError):
            # Existing manual capture remains available before migration 047.
            config = None
    return apply_available_tools(text, await agent_available_tools(agent_id, text, tenant_id=tenant_id),
                                 followup_config=config)


def capabilities_section_present(compiled_text: str | None) -> bool:
    return bool(_CAPABILITIES_HEADER_RE.search(compiled_text or ""))


def order_confirmation_allowed(compiled_text: str | None) -> bool:
    """Fail-closed runtime permission read from the compiled section."""
    text = compiled_text or ""
    match = _ORDER_CAP_LINE.search(text)
    if match:
        return match.group(1) == "allowed"
    # A publication stored before the capability section existed carries no
    # permission marker; classify its business script once at render time
    # rather than trusting platform safety text that also mentions orders.
    if capabilities_section_present(text):
        return False
    return order_confirmation_allowed_from_script(text)
