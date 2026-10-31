"""Pre-recorded technical-failure announcement for live PSTN calls.

Clips are rendered by a voice service at build time, never at call time, so the
caller still hears a professional message when the configured TTS/LLM is the
thing that failed.

Two message variants exist because "we will call you again" is a promise:

* ``callback_promise`` — only used after an automatic retry is committed to the
  follow-up queue (which applies DND, calling windows and attempt limits).
* ``call_back`` — the safe variant when no automatic retry is queued (follow-ups
  not authorized, review mode, DND / opt-out, or the daily retry limit).

Clip order: tenant upload > the agent-voice render made at call setup
(``outage_clip_prewarm``) > the shipped platform clip in a stock voice.
When it plays is defined by ``TECHNICAL_TRIGGERS`` and the failure thresholds
below.

Tenants may upload their own clip per language/variant; the platform clip is the
fallback. A tenant's typed text is never synthesized during an outage.
"""
from __future__ import annotations

import asyncio
import re
import uuid
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from server.services.audio_transcode import pcm16_to_alaw, pcm16_to_mulaw, pcm_resample
from server.utils.logger import log_pstn

_AUDIO_DIR = Path(__file__).resolve().parents[1] / "static" / "audio" / "fallback"
_CLIP_RATE = 8000
_DEFAULT_LANGUAGE = "en-IN"
_GENDERS = ("male", "female")
_DEFAULT_GENDER = "male"

CALLBACK_PROMISE = "callback_promise"
CALL_BACK = "call_back"
DISCLOSURE_VARIANT = "disclosure"
FALLBACK_VARIANTS: tuple[str, ...] = (CALLBACK_PROMISE, CALL_BACK)
CLIP_VARIANTS: tuple[str, ...] = (CALLBACK_PROMISE, CALL_BACK, DISCLOSURE_VARIANT)
DEFAULT_FALLBACK_VARIANT = CALL_BACK

#: 300–500 ms of silence after the last frame before the carrier is released.
FALLBACK_TAIL_SEC = 0.4
#: Pause after clearing the failed reply. The carrier still holds a short
#: jitter buffer, so emitting immediately clips the apology's first word.
FALLBACK_SETTLE_SEC = 0.45
#: A clip that cannot be emitted inside its own duration plus this grace is a
#: broken wire, not slow speech; hang up immediately and record a defect.
FALLBACK_WATCHDOG_GRACE_SEC = 8.0
_FALLBACK_DB_TIMEOUT_SEC = 2.0

# ---------------------------------------------------------------------------
# When the outage clip plays (the trigger threshold)
# ---------------------------------------------------------------------------
#: Failures that may end a call with the outage clip. Anything else (caller
#: silence, barge-in, a cancelled turn, a slow turn that recovered) never does.
TECHNICAL_TRIGGERS: frozenset[str] = frozenset({
    "tts_failure",          # the reply's TTS produced no audio (classic loop)
    "farewell_tts_failure",  # the closing line's TTS produced no audio
    "llm_failure",          # sustained LLM failure (see thresholds below)
    "runtime_failure",      # native-audio provider unavailable at start
    "provider_failure",     # native-audio provider died mid-call
    "response_failure",     # native-audio response failed
})
#: A *failed turn* is counted only after the orchestrator's own recovery is
#: spent: the composed transport's single larger retry and the reply watchdog's
#: single re-ask (``live_turn_orchestrator`` / ``PstnVoiceLoop._watched_turn_stream``)
#: and only when nothing of the reply reached the caller. Composed calls are
#: pinned to one provider/model (no secondary LLM is configurable), so after
#: those retries there is nothing else to try.
#:
#: * transient errors (timeouts, 5xx, truncated output): the first failed turn
#:   gets one spoken "please repeat" and keeps listening; the second
#:   *consecutive* failed turn plays the outage clip and hangs up. Any turn
#:   that completes resets the count, so one slow turn never ends a call.
#: * hard errors (auth / billing / quota / credits / model unavailable): the
#:   provider will not recover within this call, so the first failed turn plays
#:   the clip at once instead of asking the caller to repeat into a dead model.
TRANSIENT_FAILURE_THRESHOLD = 2
HARD_FAILURE_THRESHOLD = 1
_HARD_STATUS = frozenset({401, 402, 403, 404})
_HARD_ERROR_RE = re.compile(
    r"insufficient|credit|quota|billing|payment|unauthori[sz]ed|forbidden|invalid\s+api\s*key|"
    r"api\s*key|permission\s+denied|account\s+(?:suspended|disabled)|model\s+(?:not\s+found|is\s+unavailable)|"
    r"\bis\s+unavailable\b|\b40[1234]\b",
    re.IGNORECASE,
)
#: How soon the outage retry is due (the follow-up worker still moves it into
#: the agent's calling window and applies DND / attempt / daily limits).
OUTAGE_RETRY_DELAY_MIN = 15
#: One outage retry per number per day; a retry call that also hits an outage
#: does not schedule another one.
OUTAGE_RETRY_WINDOW_HOURS = 24
OUTAGE_RETRY_EXPIRY_DAYS = 2


def classify_reply_failure(exc: BaseException | None) -> str:
    """``"hard"`` when the provider cannot recover inside this call, else ``"transient"``."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attr in ("status_code", "status", "http_status"):
            value = getattr(current, attr, None)
            try:
                if int(value) in _HARD_STATUS:
                    return "hard"
            except (TypeError, ValueError):
                pass
        if type(current).__name__ in {"AuthenticationError", "PermissionDeniedError", "PaymentRequiredError"}:
            return "hard"
        if _HARD_ERROR_RE.search(str(current) or ""):
            return "hard"
        current = current.__cause__ or current.__context__
    return "transient"


def failure_threshold(kind: str) -> int:
    return HARD_FAILURE_THRESHOLD if kind == "hard" else TRANSIENT_FAILURE_THRESHOLD
_CALLBACK_TARGET_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_DISCLOSURE_RE = re.compile(
    r"record|recording|recorded|రికార్డ|रिकॉर्ड|रेकॉर्ड|பதிவ|ರೆಕಾರ್ಡ|റെക്കോർഡ|রেকর্ড",
    re.IGNORECASE,
)

FALLBACK_TEXT: dict[str, dict[str, str]] = {
    CALLBACK_PROMISE: {
        "en-IN": "Sorry, we are facing a technical problem. We will call you again. Thank you.",
        "hi-IN": "क्षमा करें, हमें एक तकनीकी समस्या आ रही है। हम आपको फिर से कॉल करेंगे। धन्यवाद।",
        "te-IN": "క్షమించండి, మాకు ఒక సాంకేతిక సమస్య ఎదురైంది. మేము మీకు మళ్లీ కాల్ చేస్తాము. ధన్యవాదాలు.",
        "ta-IN": "மன்னிக்கவும், எங்களுக்கு ஒரு தொழில்நுட்பச் சிக்கல் உள்ளது. நாங்கள் உங்களை மீண்டும் அழைப்போம். நன்றி.",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ನಮಗೆ ಒಂದು ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆ ಎದುರಾಗಿದೆ. ನಾವು ನಿಮಗೆ ಮತ್ತೆ ಕರೆ ಮಾಡುತ್ತೇವೆ. ಧನ್ಯವಾದಗಳು.",
        "ml-IN": "ക്ഷമിക്കണം, ഞങ്ങൾക്ക് ഒരു സാങ്കേതിക പ്രശ്നം നേരിടുന്നു. ഞങ്ങൾ നിങ്ങളെ വീണ്ടും വിളിക്കും. നന്ദി.",
        "mr-IN": "क्षमस्व, आम्हाला एक तांत्रिक अडचण येत आहे. आम्ही तुम्हाला पुन्हा कॉल करू. धन्यवाद.",
        "bn-IN": "দুঃখিত, আমরা একটি প্রযুক্তিগত সমস্যার সম্মুখীন হচ্ছি। আমরা আপনাকে আবার কল করব। ধন্যবাদ।",
        "gu-IN": "માફ કરશો, અમને તકનીકી સમસ્યા આવી રહી છે. અમે તમને ફરીથી કૉલ કરીશું. આભાર.",
        "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਸਾਨੂੰ ਇੱਕ ਤਕਨੀਕੀ ਸਮੱਸਿਆ ਦਾ ਸਾਹਮਣਾ ਕਰਨਾ ਪੈ ਰਿਹਾ ਹੈ। ਅਸੀਂ ਤੁਹਾਨੂੰ ਦੁਬਾਰਾ ਕਾਲ ਕਰਾਂਗੇ। ਧੰਨਵਾਦ।",
    },
    CALL_BACK: {
        "en-IN": "Sorry, we are facing a technical problem. Please call us back. Thank you.",
        "hi-IN": "क्षमा करें, हमें एक तकनीकी समस्या आ रही है। कृपया हमें वापस कॉल करें। धन्यवाद।",
        "te-IN": "క్షమించండి, మాకు ఒక సాంకేతిక సమస్య ఎదురైంది. దయచేసి మాకు తిరిగి కాల్ చేయండి. ధన్యవాదాలు.",
        "ta-IN": "மன்னிக்கவும், எங்களுக்கு ஒரு தொழில்நுட்பச் சிக்கல் உள்ளது. தயவுசெய்து எங்களை மீண்டும் அழைக்கவும். நன்றி.",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ನಮಗೆ ಒಂದು ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆ ಎದುರಾಗಿದೆ. ದಯವಿಟ್ಟು ನಮಗೆ ಮತ್ತೆ ಕರೆ ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.",
        "ml-IN": "ക്ഷമിക്കണം, ഞങ്ങൾക്ക് ഒരു സാങ്കേതിക പ്രശ്നം നേരിടുന്നു. ദയവായി ഞങ്ങളെ വീണ്ടും വിളിക്കുക. നന്ദി.",
        "mr-IN": "क्षमस्व, आम्हाला एक तांत्रिक अडचण येत आहे. कृपया आम्हाला परत कॉल करा. धन्यवाद.",
        "bn-IN": "দুঃখিত, আমরা একটি প্রযুক্তিগত সমস্যার সম্মুখীন হচ্ছি। অনুগ্রহ করে আমাদের আবার কল করুন। ধন্যবাদ।",
        "gu-IN": "માફ કરશો, અમને તકનીકી સમસ્યા આવી રહી છે. કૃપા કરીને અમને ફરીથી કૉલ કરો. આભાર.",
        "pa-IN": "ਮਾਫ਼ ਕਰਨਾ, ਸਾਨੂੰ ਇੱਕ ਤਕਨੀਕੀ ਸਮੱਸਿਆ ਦਾ ਸਾਹਮਣਾ ਕਰਨਾ ਪੈ ਰਿਹਾ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ ਦੁਬਾਰਾ ਕਾਲ ਕਰੋ। ਧੰਨਵਾਦ।",
    },
    DISCLOSURE_VARIANT: {
        "en-IN": "This call is being recorded for quality and training purposes.",
        "hi-IN": "यह कॉल गुणवत्ता और प्रशिक्षण उद्देश्यों के लिए रिकॉर्ड की जा रही है।",
        "te-IN": "ఈ కాల్ నాణ్యత మరియు శిక్షణ ప్రయోజనాల కోసం రికార్డ్ చేయబడుతోంది.",
        "ta-IN": "இந்த அழைப்பு தரம் மற்றும் பயிற்சி நோக்கங்களுக்காகப் பதிவு செய்யப்படுகிறது.",
        "kn-IN": "ಈ ಕರೆ ಗುಣಮಟ್ಟ ಮತ್ತು ತರಬೇತಿ ಉದ್ದೇಶಗಳಿಗಾಗಿ ರೆಕಾರ್ಡ್ ಆಗುತ್ತಿದೆ.",
        "ml-IN": "ഈ കോൾ ഗുണനിലവാരത്തിനും പരിശീലനത്തിനുമായി റെക്കോർഡ് ചെയ്യപ്പെടുന്നു.",
        "mr-IN": "हा कॉल गुणवत्ता आणि प्रशिक्षणाच्या उद्देशाने रेकॉर्ड केला जात आहे.",
        "bn-IN": "এই কলটি গুণমান ও প্রশিক্ষণের উদ্দেশ্যে রেকর্ড করা হচ্ছে।",
        "gu-IN": "આ કૉલ ગુણવત્તા અને તાલીમના હેતુ માટે રેકોર્ડ થઈ રહ્યો છે.",
        "pa-IN": "ਇਹ ਕਾਲ ਗੁਣਵੱਤਾ ਅਤੇ ਸਿਖਲਾਈ ਦੇ ਉਦੇਸ਼ ਲਈ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਰਹੀ ਹੈ।",
    },
}


def _normalize_language(language: str | None) -> str:
    return (language or "").strip().replace("_", "-")


def resolve_fallback_language(language: str | None) -> str:
    """Pick the shipped clip for a call language, preferring the same base language."""
    raw = _normalize_language(language)
    if not raw:
        return _DEFAULT_LANGUAGE
    for code in FALLBACK_TEXT[CALL_BACK]:
        if code.casefold() == raw.casefold():
            return code
    base = raw.split("-", 1)[0].casefold()
    if base == "en":
        return "en-IN"
    for code in FALLBACK_TEXT[CALL_BACK]:
        if code.split("-", 1)[0].casefold() == base:
            return code
    return _DEFAULT_LANGUAGE


def fallback_text(language: str | None, variant: str = DEFAULT_FALLBACK_VARIANT) -> str:
    key = variant if variant in FALLBACK_TEXT else DEFAULT_FALLBACK_VARIANT
    return FALLBACK_TEXT[key][resolve_fallback_language(language)]


@lru_cache(maxsize=64)
def _load_pcm(variant: str, gender: str, language: str) -> bytes:
    path = _AUDIO_DIR / variant / gender / f"{language}.wav"
    try:
        with wave.open(str(path), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                raise ValueError("fallback clip must be mono 16-bit PCM")
            frames = source.readframes(source.getnframes())
            rate = source.getframerate()
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        log_pstn(
            "fallback.asset_missing",
            variant=variant,
            gender=gender,
            language=language,
            error=str(exc)[:160],
        )
        return b""
    if rate != _CLIP_RATE and frames:
        frames = pcm_resample(frames, rate, _CLIP_RATE)
    return frames


def _wire_family(output_codec: str | None) -> str | None:
    codec = str(output_codec or "").strip().lower()
    if codec in {"mulaw", "ulaw", "pcmu", "g711u"}:
        return "pcmu"
    if codec in {"alaw", "pcma", "g711a"}:
        return "pcma"
    if codec in {"linear16", "l16", "pcm16"}:
        return "l16"
    return None


def pcm_wire_frames(
    pcm: bytes,
    *,
    output_codec: str | None,
    sample_rate: int,
) -> list[bytes]:
    """Frames the carrier expects for one 8 kHz mono PCM16 clip."""
    family = _wire_family(output_codec)
    if family is None or not pcm:
        return []
    if family == "l16":
        rate = sample_rate if sample_rate > 0 else _CLIP_RATE
        if rate != _CLIP_RATE:
            pcm = pcm_resample(pcm, _CLIP_RATE, rate)
        frame_bytes = max(2, int(rate * 0.02) * 2)
        return [pcm[offset:offset + frame_bytes] for offset in range(0, len(pcm), frame_bytes)]
    encoded = pcm16_to_mulaw(pcm, _CLIP_RATE) if family == "pcmu" else pcm16_to_alaw(pcm, _CLIP_RATE)
    return [encoded[offset:offset + 160] for offset in range(0, len(encoded), 160)]


def fallback_wire_frames(
    language: str | None,
    *,
    output_codec: str | None,
    sample_rate: int,
    variant: str = DEFAULT_FALLBACK_VARIANT,
    gender: str = _DEFAULT_GENDER,
) -> list[bytes]:
    """Platform clip frames, already in the loop's wire codec."""
    if _wire_family(output_codec) is None:
        log_pstn("fallback.codec_unsupported", language=language, codec=str(output_codec)[:24])
        return []
    resolved = resolve_fallback_language(language)
    wanted = gender if gender in _GENDERS else _DEFAULT_GENDER
    pcm = _load_pcm(variant, wanted, resolved)
    if not pcm and wanted != _DEFAULT_GENDER:
        pcm = _load_pcm(variant, _DEFAULT_GENDER, resolved)
    return pcm_wire_frames(pcm, output_codec=output_codec, sample_rate=int(sample_rate or _CLIP_RATE))


@dataclass(frozen=True)
class FallbackClip:
    pcm: bytes
    language: str
    source: str = "none"


@dataclass(frozen=True)
class FallbackPlan:
    variant: str
    language: str
    source: str
    gender: str
    pcm: bytes
    text: str
    disclosure_pcm: bytes = b""
    disclosure_language: str = ""
    disclosure_text: str = ""
    callback_task_id: str | None = None
    defect: str | None = None
    retry_status: str = ""
    opted_out: bool = False

    @property
    def has_audio(self) -> bool:
        return bool(self.pcm)

    def technical_frames(self, *, output_codec: str | None, sample_rate: int) -> list[bytes]:
        return pcm_wire_frames(self.pcm, output_codec=output_codec, sample_rate=sample_rate)

    def disclosure_frames(self, *, output_codec: str | None, sample_rate: int) -> list[bytes]:
        return pcm_wire_frames(self.disclosure_pcm, output_codec=output_codec, sample_rate=sample_rate)

    def watchdog_sec(self) -> float:
        pcm = self.disclosure_pcm + self.pcm
        return len(pcm) / 16000.0 + FALLBACK_WATCHDOG_GRACE_SEC


@dataclass
class TenantFallbackConfig:
    available: bool = False
    promise_callback: bool = True
    clips: dict[tuple[str, str], bytes] = field(default_factory=dict)
    callback_task_id: str | None = None
    #: True only when an automatic retry is queued, so "we will call you" is kept.
    callback_created: bool = False
    note_text: str = ""
    #: scheduled | existing | needs_review | skipped:<reason> | "" (not attempted)
    retry_status: str = ""


def _read_meta(call_id: str | None) -> dict[str, Any]:
    if not call_id:
        return {}
    try:
        from server.call.call_ledger import call_ledger

        return call_ledger.read_meta(call_id) or {}
    except Exception:
        return {}


def _read_transcript(call_id: str | None) -> list[dict[str, Any]]:
    if not call_id:
        return []
    try:
        from server.call.call_ledger import call_ledger

        return call_ledger.read_lines(call_id)
    except Exception:
        return []


def _normalize_target(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-().]", "", raw)
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    elif cleaned.startswith("+"):
        pass
    elif cleaned.isdigit():
        # Stored numbers are frequently E.164 digits without the plus sign
        # (``918897908470``); treating those as invalid silently downgraded
        # every promised callback to the safe "call us back" clip.
        if len(cleaned) == 10:
            cleaned = f"+91{cleaned}"
        elif len(cleaned) == 11 and cleaned.startswith("0"):
            cleaned = f"+91{cleaned[1:]}"
        else:
            cleaned = f"+{cleaned}"
    return cleaned if _CALLBACK_TARGET_RE.fullmatch(cleaned) else None


def callback_target(meta: dict[str, Any], direction: str | None) -> str | None:
    """The remote party to dial back: callee on outbound, caller on inbound."""
    going_out = str(direction or meta.get("direction") or "").strip().lower().startswith("out")
    keys = (
        ("callee_e164", "to_e164", "to_number", "called_e164")
        if going_out
        else ("caller_id", "from_e164", "caller_phone", "from_number")
    )
    for key in keys:
        target = _normalize_target(meta.get(key))
        if target:
            return target
    return None


def _disclosure_needed(meta: dict[str, Any], transcript: list[dict[str, Any]]) -> bool:
    info = meta.get("recording_disclosure")
    if not isinstance(info, dict) or not info.get("enabled"):
        return False
    for row in transcript:
        if str(row.get("role") or "").lower() not in ("assistant", "agent"):
            continue
        if _DISCLOSURE_RE.search(str(row.get("text") or "")):
            return False
    return True


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


async def _schedule_outage_retry(
    session: Any,
    *,
    tenant_uuid: uuid.UUID,
    agent_uuid: uuid.UUID,
    call_id: str,
    target: str,
) -> tuple[str | None, str]:
    """Queue "we'll call you back" on the follow-up worker; returns (job id, status).

    The follow-up queue is the platform's only redial path, so the retry gets
    every rule it enforces at dispatch: tenant authorization and review mode,
    DND, the agent's calling window and weekdays, attempt / daily / cooldown
    limits and expiry. Nothing here dials. Statuses:

    * ``scheduled`` / ``existing`` - an automatic retry is queued (promise kept)
    * ``needs_review`` - queued for the tenant to approve (no spoken promise)
    * ``skipped:<reason>`` - no follow-ups authorized, DND, or retry limit
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob
    from server.db.models.phase5_models import DncEntry
    from server.services.saas.followup_policy import FollowUpConfig

    policy = await session.scalar(
        select(AgentFollowUpPolicy).where(
            AgentFollowUpPolicy.tenant_id == tenant_uuid,
            AgentFollowUpPolicy.agent_id == agent_uuid,
        )
    )
    if policy is None or policy.authorized_by is None:
        return None, "skipped:followups_not_authorized"
    cfg = FollowUpConfig.model_validate(policy.config or {})
    if not cfg.enabled:
        return None, "skipped:followups_disabled"
    if await session.scalar(
        select(DncEntry.id).where(
            DncEntry.tenant_id == tenant_uuid,
            DncEntry.phone_e164 == target,
            DncEntry.active.is_(True),
        )
    ):
        return None, "skipped:do_not_call"
    origin_key = f"technical:{call_id}"[:120]
    own = await session.scalar(
        select(FollowUpJob).where(FollowUpJob.tenant_id == tenant_uuid, FollowUpJob.origin_key == origin_key)
    )
    if own is not None:
        return str(own.id), "existing" if own.status == "scheduled" else str(own.status)
    now = datetime.now(timezone.utc)
    pending = await session.scalar(
        select(FollowUpJob).where(
            FollowUpJob.tenant_id == tenant_uuid,
            FollowUpJob.agent_id == agent_uuid,
            FollowUpJob.phone == target,
            FollowUpJob.kind == "callback",
            FollowUpJob.status.in_(("planning", "resolving", "scheduled")),
        ).limit(1)
    )
    if pending is not None:
        # The caller already has a callback coming; do not stack a second one.
        return str(pending.id), "existing"
    recent = await session.scalar(
        select(FollowUpJob.id).where(
            FollowUpJob.tenant_id == tenant_uuid,
            FollowUpJob.phone == target,
            FollowUpJob.origin_key.like("technical:%"),
            FollowUpJob.created_at >= now - timedelta(hours=OUTAGE_RETRY_WINDOW_HOURS),
        ).limit(1)
    )
    if recent is not None:
        return None, "skipped:retry_limit"
    automatic = cfg.callbackMode == "automatic"
    job = FollowUpJob(
        tenant_id=tenant_uuid,
        agent_id=agent_uuid,
        origin_key=origin_key,
        source_id=str(call_id)[:36],
        kind="callback",
        phone=target,
        status="scheduled" if automatic else "needs_review",
        reason="technical_failure_retry" if automatic else "approval_required",
        payload={
            "origin": "technical_failure",
            "requestText": "",
            "requestedWhen": "",
            "timezone": cfg.timezone,
            "requestedAt": now.isoformat(),
        },
        due_at=now + timedelta(minutes=OUTAGE_RETRY_DELAY_MIN) if automatic else None,
        expires_at=now + timedelta(days=min(cfg.expiryDays, OUTAGE_RETRY_EXPIRY_DAYS)),
        authorized_by=policy.authorized_by,
        billing_tenant_id=policy.billing_tenant_id,
    )
    session.add(job)
    await session.flush()
    return str(job.id), "scheduled" if automatic else "needs_review"


async def _load_tenant_config(
    *,
    tenant_id: str | None,
    agent_id: str | None,
    call_id: str | None,
    target: str | None,
    promise_allowed: bool = True,
) -> TenantFallbackConfig:
    """Load agent promise setting + uploaded clips, creating the callback row first.

    Any DB problem degrades to the safe ``call_back`` variant and platform clips:
    the caller must never hear a promise the system did not persist.
    """
    tenant_uuid = _uuid_or_none(tenant_id)
    agent_uuid = _uuid_or_none(agent_id)
    if tenant_uuid is None or agent_uuid is None:
        return TenantFallbackConfig(available=False, promise_callback=False)

    from server.db.connection import get_session_factory

    factory = get_session_factory()
    if factory is None:
        return TenantFallbackConfig(available=False, promise_callback=False)

    async def _work() -> TenantFallbackConfig:
        from sqlalchemy import select

        from server.db.models.entities import Agent, AgentFallbackClip

        async with factory() as session:
            result = await session.execute(
                select(Agent).where(
                    Agent.agent_id == agent_uuid,
                    Agent.tenant_id == tenant_uuid,
                )
            )
            agent = result.scalar_one_or_none()
            if agent is None:
                return TenantFallbackConfig(available=False, promise_callback=False)

            clip_rows = await session.execute(
                select(AgentFallbackClip).where(
                    AgentFallbackClip.agent_id == agent_uuid,
                    AgentFallbackClip.tenant_id == tenant_uuid,
                )
            )
            clips = {
                (
                    _normalize_language(row.language).casefold(),
                    str(row.variant or ""),
                ): bytes(row.pcm_bytes or b"")
                for row in clip_rows.scalars().all()
                if row.pcm_bytes
            }

            config = TenantFallbackConfig(
                available=True,
                promise_callback=bool(agent.technical_fallback_promise_callback) and promise_allowed,
                clips=clips,
                note_text=str(agent.technical_fallback_text or "").strip(),
            )
            if not (config.promise_callback and target and call_id):
                config.retry_status = "skipped:not_allowed" if target else "skipped:no_target"
                return config

            try:
                job_id, status = await _schedule_outage_retry(
                    session,
                    tenant_uuid=tenant_uuid,
                    agent_uuid=agent_uuid,
                    call_id=str(call_id),
                    target=target,
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                log_pstn("fallback.retry.failed", call_id=call_id, error=type(exc).__name__)
                job_id, status = None, "skipped:storage_error"
            config.retry_status = status
            config.callback_task_id = job_id
            # Only an automatic, queued retry backs the spoken promise; a job
            # waiting for review may never be approved.
            config.callback_created = bool(job_id) and status in ("scheduled", "existing")
            return config

    try:
        return await asyncio.wait_for(_work(), timeout=_FALLBACK_DB_TIMEOUT_SEC)
    except Exception as exc:
        log_pstn(
            "fallback.tenant_config.failed",
            call_id=call_id,
            error=type(exc).__name__,
        )
        return TenantFallbackConfig(available=False, promise_callback=False)


def _custom_clip(
    clips: dict[tuple[str, str], bytes],
    language: str,
    variant: str,
) -> FallbackClip | None:
    for candidate in (language, _DEFAULT_LANGUAGE):
        pcm = clips.get((_normalize_language(candidate).casefold(), variant))
        if pcm:
            return FallbackClip(pcm=pcm, language=_normalize_language(candidate), source="custom")
    return None


def _agent_voice_clip(
    *,
    tenant_id: str | None,
    agent_id: str | None,
    language: str,
    variant: str,
    resolved_stack: Any | None,
    stack_override: dict[str, Any] | None,
) -> FallbackClip | None:
    """The clip rendered at call setup in the call's own TTS voice, if any."""
    if resolved_stack is None and not stack_override:
        return None
    try:
        from server.services.outage_clip_prewarm import agent_voice_clip

        pcm = agent_voice_clip(
            tenant_id=tenant_id,
            agent_id=agent_id,
            language=language,
            variant=variant,
            resolved_stack=resolved_stack,
            stack_override=stack_override,
        )
    except Exception:
        return None
    if not pcm:
        return None
    return FallbackClip(pcm=pcm, language=resolve_fallback_language(language), source="agent_voice")


def _platform_clip(language: str, variant: str, gender: str) -> FallbackClip:
    wanted = gender if gender in _GENDERS else _DEFAULT_GENDER
    resolved = resolve_fallback_language(language)
    for code in (resolved, _DEFAULT_LANGUAGE):
        for candidate_gender in (wanted, _DEFAULT_GENDER):
            pcm = _load_pcm(variant, candidate_gender, code)
            if pcm:
                return FallbackClip(pcm=pcm, language=code, source="platform")
    return FallbackClip(pcm=b"", language=resolved, source="none")


def _select_clip(
    clips: dict[tuple[str, str], bytes],
    language: str,
    variant: str,
    gender: str,
) -> FallbackClip:
    return _custom_clip(clips, language, variant) or _platform_clip(language, variant, gender)


@lru_cache(maxsize=16)
def _voice_gender(provider: str, model: str, voice_id: str) -> str:
    try:
        from server.providers.voice_inventory import voices_for_model

        wanted = voice_id.strip().casefold()
        for row in voices_for_model(provider, model):
            candidates = {
                str(row.get("id") or "").casefold(),
                str(row.get("providerVoiceId") or "").casefold(),
            }
            if wanted in candidates:
                gender = str(row.get("gender") or "").strip().lower()
                if gender in _GENDERS:
                    return gender
    except Exception:
        pass
    return _DEFAULT_GENDER


def resolve_voice_gender(
    *,
    provider: str | None,
    model: str | None,
    voice_id: str | None,
) -> str:
    if not (provider and model and voice_id):
        return _DEFAULT_GENDER
    return _voice_gender(str(provider), str(model), str(voice_id))


def infer_voice_identity(
    *,
    resolved_stack: Any | None = None,
    stack_override: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Best-effort (provider, model, voice) for matching the agent's gender."""
    override = stack_override or {}
    realtime = override.get("realtime_voice") if isinstance(override.get("realtime_voice"), dict) else {}
    llm = override.get("llm") if isinstance(override.get("llm"), dict) else {}
    if realtime.get("voice"):
        return (
            str(llm.get("provider") or "gemini"),
            str(llm.get("model") or ""),
            str(realtime.get("voice") or ""),
        )
    if resolved_stack is not None:
        tts = getattr(resolved_stack, "tts", None)
        config = getattr(tts, "config", None) or {}
        voice = config.get("speaker") or config.get("voice_id") or config.get("voice") or ""
        return (
            str(getattr(tts, "provider", "") or ""),
            str(getattr(tts, "model", "") or ""),
            str(voice),
        )
    return ("", "", "")


async def prepare_technical_fallback_plan(
    *,
    call_id: str | None,
    tenant_id: str | None,
    agent_id: str | None,
    direction: str | None,
    language: str | None,
    trigger: str,
    voice_provider: str | None = None,
    voice_model: str | None = None,
    voice_id: str | None = None,
    pending_user_text: str | None = None,
    resolved_stack: Any | None = None,
    stack_override: dict[str, Any] | None = None,
) -> FallbackPlan:
    """Resolve what the caller hears, whether a retry is queued, and record an opt-out.

    ``pending_user_text`` is the caller turn the failed model never answered.
    It is checked (with every earlier caller line) by the deterministic opt-out
    detector, because no model is available to read it: a do-not-call request
    is recorded and suppresses the retry.
    """
    from server.services.speech_outage_config import load_speech_outage_config

    meta = _read_meta(call_id)
    transcript = _read_transcript(call_id)
    from server.call.end_call_validate import caller_firm_refusal, caller_requested_hangup
    from server.services.outage_opt_out import opt_out_in_transcript, record_outage_opt_out

    last_user = (pending_user_text or "").strip() or next(
        (str(row.get("text") or "") for row in reversed(transcript) if row.get("role") == "user"),
        "",
    )
    opted_out = str(meta.get("contact_preference") or "").lower() == "do_not_call"
    evidence = opt_out_in_transcript(transcript, pending_user_text)
    if evidence and not opted_out:
        await record_outage_opt_out(call_id, evidence)
    opted_out = opted_out or bool(evidence)
    if opted_out:
        log_pstn("fallback.retry.suppressed", call_id=call_id, reason="do_not_call")
    callback_allowed = (
        trigger in TECHNICAL_TRIGGERS
        and not opted_out
        and not caller_firm_refusal(last_user)
        and not caller_requested_hangup(last_user)
    )
    admitted_language = _normalize_language(language) or _DEFAULT_LANGUAGE
    target = callback_target(meta, direction)
    outage = await load_speech_outage_config()
    gender = resolve_voice_gender(provider=voice_provider, model=voice_model, voice_id=voice_id)
    if not outage.enabled:
        # The platform switch is authoritative and stops both the spoken
        # announcement and any new callback promise it would have made.
        log_pstn("fallback.disabled", call_id=call_id, reason=trigger)
        return FallbackPlan(
            variant=CALL_BACK,
            language=admitted_language,
            source="none",
            gender=gender,
            pcm=b"",
            text="",
            defect="announcement_disabled",
        )
    config = await _load_tenant_config(
        tenant_id=tenant_id,
        agent_id=agent_id,
        call_id=call_id,
        target=target,
        promise_allowed=outage.promise_callback and callback_allowed,
    )

    variant = CALLBACK_PROMISE if config.callback_created else CALL_BACK
    clip = _custom_clip(config.clips, admitted_language, variant) or _agent_voice_clip(
        tenant_id=tenant_id,
        agent_id=agent_id,
        language=admitted_language,
        variant=variant,
        resolved_stack=resolved_stack,
        stack_override=stack_override,
    ) or _select_clip(config.clips, admitted_language, variant, gender)
    defect = None if clip.pcm else "asset_missing"
    if defect:
        log_pstn(
            "fallback.asset_missing",
            call_id=call_id,
            variant=variant,
            language=admitted_language,
            reason=trigger,
        )
    if clip.source == "custom":
        spoken_text = config.note_text or FALLBACK_TEXT[variant]["en-IN"]
    else:
        spoken_text = FALLBACK_TEXT[variant].get(clip.language, FALLBACK_TEXT[variant]["en-IN"]) if clip.pcm else ""

    disclosure_pcm = b""
    disclosure_language = ""
    disclosure_text = ""
    if _disclosure_needed(meta, transcript):
        disclosure = _select_clip(config.clips, admitted_language, DISCLOSURE_VARIANT, gender)
        if disclosure.pcm:
            disclosure_pcm = disclosure.pcm
            disclosure_language = disclosure.language
            disclosure_text = FALLBACK_TEXT[DISCLOSURE_VARIANT].get(
                disclosure.language,
                FALLBACK_TEXT[DISCLOSURE_VARIANT]["en-IN"],
            )
        else:
            log_pstn(
                "disclosure_not_delivered",
                call_id=call_id,
                reason=trigger,
                language=admitted_language,
            )

    return FallbackPlan(
        variant=variant,
        language=clip.language if clip.pcm else admitted_language,
        source=clip.source,
        gender=gender,
        pcm=clip.pcm,
        text=spoken_text,
        disclosure_pcm=disclosure_pcm,
        disclosure_language=disclosure_language,
        disclosure_text=disclosure_text,
        callback_task_id=config.callback_task_id,
        defect=defect,
        retry_status="skipped:do_not_call" if opted_out else config.retry_status,
        opted_out=opted_out,
    )


def platform_clip_coverage() -> dict[str, dict[str, list[str]]]:
    """Languages with a shipped platform clip, per variant and voice gender."""
    return {
        variant: {
            gender: [code for code in FALLBACK_TEXT[variant] if _load_pcm(variant, gender, code)]
            for gender in _GENDERS
        }
        for variant in CLIP_VARIANTS
    }


def stamp_fallback_meta(
    call_id: str | None,
    plan: FallbackPlan,
    *,
    trigger: str,
    played: bool,
    disclosure_played: bool = False,
    defect: str | None = None,
) -> None:
    if not call_id:
        return
    try:
        from server.call.call_ledger import call_ledger

        meta = call_ledger.read_meta(call_id) or {}
        meta["fallback_played"] = bool(played)
        meta["fallback_language"] = plan.language
        meta["fallback_reason"] = trigger
        meta["fallback_variant"] = plan.variant
        meta["fallback_source"] = plan.source
        meta["fallback_disclosure_played"] = bool(disclosure_played)
        if plan.callback_task_id:
            meta["fallback_callback_task_id"] = plan.callback_task_id
        if plan.retry_status:
            meta["fallback_retry_status"] = plan.retry_status
        if plan.opted_out:
            meta["fallback_opt_out_honoured"] = True
        # One flag every consumer (calls list, analytics) can read without
        # re-deriving it from the end reason.
        meta["technical_failure"] = True
        if plan.disclosure_text and not disclosure_played:
            meta["fallback_disclosure_not_delivered"] = True
        if defect or plan.defect:
            meta["fallback_defect"] = str(defect or plan.defect)
        call_ledger.write_meta(call_id, meta)
    except Exception as exc:
        log_pstn("fallback.meta.failed", call_id=call_id, error=str(exc)[:160])
