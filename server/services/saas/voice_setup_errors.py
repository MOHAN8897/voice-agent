"""Tenant-safe preparation errors shared by browser and phone tests."""
from server.services.saas.voice_stack_profiles import VoiceProfileError
from server.utils.errors import AppError, ErrorCode

VOICE_SETUP_MESSAGES = {
    "profile_revision_conflict": "Your saved voice setup has changed. Open Voice, refresh the choices and select a voice again.",
    "voice_selection_invalid": "Choose a voice from the current Voice setup before testing this agent.",
    "unsupported_language": "Choose a voice setup that supports the agent's language before testing.",
    "profile_unavailable": "This voice setup is unavailable. Choose an available option in Voice or ask your administrator to repair it.",
    "voice_setup_invalid": "This voice setup is not ready for calls. Ask your administrator to check its model, voice and connection settings.",
}


def voice_setup_error(exc: Exception) -> dict[str, str] | None:
    if isinstance(exc, VoiceProfileError):
        code = exc.code if exc.code in VOICE_SETUP_MESSAGES else "voice_setup_invalid"
    elif isinstance(exc, AppError) and exc.code in {ErrorCode.VALIDATION_ERROR, ErrorCode.CONFIG_ERROR, ErrorCode.PROVIDER_DISABLED}:
        code = "voice_setup_invalid"
    else:
        return None
    return {"code": code, "message": VOICE_SETUP_MESSAGES[code]}
