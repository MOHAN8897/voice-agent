"""
Error taxonomy — server/utils/errors.py
Maps provider errors to user-safe messages + retry decisions.
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    CONFIG_ERROR = "config_error"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    STT_EMPTY = "stt_empty"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_DISABLED = "provider_disabled"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"


# User-safe messages (never leak secrets)
USER_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.CONFIG_ERROR: "AI service configuration is invalid. Check .env — see .env.example.",
    ErrorCode.AUTH_ERROR: "AI service configuration is invalid.",
    ErrorCode.RATE_LIMIT: "Service is temporarily busy. Please try again.",
    ErrorCode.VALIDATION_ERROR: "Request was invalid. Check input length.",
    ErrorCode.NETWORK_ERROR: "Network issue. Please retry.",
    ErrorCode.TIMEOUT: "Request timed out. Please try again.",
    ErrorCode.STT_EMPTY: "Didn't catch that. Please try again.",
    ErrorCode.PROVIDER_ERROR: "AI service is temporarily unavailable. Please try again.",
    ErrorCode.PROVIDER_DISABLED: "The selected AI provider is not enabled.",
    ErrorCode.NOT_FOUND: "Resource not found.",
    ErrorCode.CONFLICT: "Request conflicts with the current call state.",
}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        status_code: int = 500,
        retryable: bool = False,
        provider: str | None = None,
        cause: Exception | None = None,
    ):
        self.code = code
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        # Never expose raw provider message if it may contain secrets
        self.user_message = message or USER_MESSAGES.get(code, "Something went wrong.")
        self.cause = cause
        super().__init__(self.user_message)

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code.value,
                "message": self.user_message,
                "provider": self.provider,
                "retryable": self.retryable,
            }
        }


def classify_http_status(status: int, provider: str) -> AppError:
    if status in (401, 403):
        return AppError(ErrorCode.AUTH_ERROR, provider=provider, status_code=status)
    if status == 429:
        return AppError(ErrorCode.RATE_LIMIT, provider=provider, status_code=429, retryable=True)
    if status in (400, 422):
        return AppError(ErrorCode.VALIDATION_ERROR, provider=provider, status_code=status)
    if 500 <= status < 600:
        return AppError(ErrorCode.PROVIDER_ERROR, provider=provider, status_code=status, retryable=True)
    return AppError(ErrorCode.PROVIDER_ERROR, provider=provider, status_code=status)
