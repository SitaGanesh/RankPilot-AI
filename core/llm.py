"""Factory for the configured Groq chat model, circuit breaker, and health validation."""

import logging
import os
import time
from typing import Any
from dotenv import load_dotenv

from .errors import LLMError

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Circuit breaker state
_circuit_breaker_opened_at: float | None = None
_circuit_breaker_reason: str | None = None
_CIRCUIT_BREAKER_TTL = 300.0  # 5 minutes
_logged_failures: set[str] = set()

# Cached validation state
_validation_cache: dict[str, Any] | None = None
_validation_cached_at: float = 0.0
_VALIDATION_TTL = 300.0  # 5 minutes


def is_circuit_open() -> tuple[bool, str | None]:
    """Check if the circuit breaker is currently open."""
    global _circuit_breaker_opened_at, _circuit_breaker_reason
    if _circuit_breaker_opened_at is not None:
        if time.monotonic() - _circuit_breaker_opened_at < _CIRCUIT_BREAKER_TTL:
            return True, _circuit_breaker_reason
        # Circuit breaker expired
        _circuit_breaker_opened_at = None
        _circuit_breaker_reason = None
    return False, None


def trip_circuit_breaker(reason: str) -> None:
    """Trip the circuit breaker on permanent errors."""
    global _circuit_breaker_opened_at, _circuit_breaker_reason
    _circuit_breaker_opened_at = time.monotonic()
    _circuit_breaker_reason = reason
    logger.warning("LLM circuit breaker TRIPPED for 5m: %s", reason)


def reset_circuit_breaker() -> None:
    """Reset circuit breaker state and cached audit failure logs."""
    global _circuit_breaker_opened_at, _circuit_breaker_reason, _logged_failures, _validation_cache, _validation_cached_at
    _circuit_breaker_opened_at = None
    _circuit_breaker_reason = None
    _logged_failures.clear()
    _validation_cache = None
    _validation_cached_at = 0.0


def log_llm_failure_once_per_audit(audit_id: str | None, message: str, *args) -> None:
    """Log an LLM failure warning at most once per audit."""
    key = str(audit_id) if audit_id else "global"
    if key not in _logged_failures:
        _logged_failures.add(key)
        logger.warning(message, *args)


def is_permanent_error(exc: Exception) -> bool:
    """Classify if an exception represents a permanent, non-retryable configuration or auth error."""
    exc_str = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    if status_code in (400, 401, 403, 404):
        return True

    exc_cls = exc.__class__.__name__
    if any(k in exc_cls for k in ("AuthenticationError", "NotFoundError", "PermissionDeniedError")):
        return True

    if "model_not_found" in exc_str or "does not exist or you do not have access" in exc_str:
        return True
    if "not support chat completions" in exc_str or "invalid_api_key" in exc_str:
        return True
    if "401" in exc_str or "403" in exc_str or "404" in exc_str:
        return True

    return False


def validate_llm_config(force_refresh: bool = False) -> dict[str, Any]:
    """Validate Groq LLM configuration with a single tiny chat completion call (cached).

    Classifies result as: ok / model_not_found / not_chat_model / auth_error / rate_limited / network_error.
    Never exposes secrets or credentials in the response.
    """
    global _validation_cache, _validation_cached_at
    now = time.monotonic()
    if not force_refresh and _validation_cache is not None and (now - _validation_cached_at < _VALIDATION_TTL):
        return _validation_cache

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key:
        result = {
            "status": "not_configured",
            "model": model or None,
            "reason": "GROQ_API_KEY environment variable is missing",
        }
        _validation_cache = result
        _validation_cached_at = now
        return result

    if not model:
        result = {
            "status": "not_configured",
            "model": None,
            "reason": "GROQ_MODEL environment variable is missing",
        }
        _validation_cache = result
        _validation_cached_at = now
        return result

    # Check if circuit breaker is already open
    is_open, open_reason = is_circuit_open()
    if is_open and not force_refresh:
        result = {
            "status": "circuit_breaker_open",
            "model": model,
            "reason": f"Circuit breaker active: {open_reason}",
        }
        return result

    try:
        from groq import Groq
        client = Groq(api_key=api_key, timeout=10.0, max_retries=0)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        result = {
            "status": "ok",
            "model": model,
            "reason": "Model is responsive and supports chat completions",
        }
    except ImportError:
        try:
            from langchain_groq import ChatGroq
            chat = ChatGroq(api_key=api_key, model=model, temperature=0.0, timeout=10.0, max_retries=0)
            chat.invoke("hi")
            result = {
                "status": "ok",
                "model": model,
                "reason": "Model is responsive and supports chat completions",
            }
        except Exception as exc:
            result = _classify_llm_exception(exc, model)
    except Exception as exc:
        result = _classify_llm_exception(exc, model)

    if result["status"] in ("auth_error", "model_not_found", "not_chat_model"):
        trip_circuit_breaker(result["reason"])

    _validation_cache = result
    _validation_cached_at = now
    return result


def _classify_llm_exception(exc: Exception, model: str) -> dict[str, Any]:
    exc_str = str(exc).lower()
    status_code = getattr(exc, "status_code", None)

    if status_code == 401 or "authentication" in exc_str or "invalid_api_key" in exc_str:
        return {
            "status": "auth_error",
            "model": model,
            "reason": "Invalid or unauthorized Groq API key",
        }
    if status_code == 404 or "model_not_found" in exc_str or "does not exist" in exc_str:
        return {
            "status": "model_not_found",
            "model": model,
            "reason": f"Model '{model}' does not exist or you do not have access",
        }
    if status_code == 400 or "does not support chat completions" in exc_str:
        return {
            "status": "not_chat_model",
            "model": model,
            "reason": f"Model '{model}' does not support chat completions",
        }
    if status_code == 429 or "rate_limit" in exc_str:
        return {
            "status": "rate_limited",
            "model": model,
            "reason": "Groq rate limit exceeded",
        }
    if "connection" in exc_str or "timed out" in exc_str or "timeout" in exc_str:
        return {
            "status": "network_error",
            "model": model,
            "reason": f"Network or timeout error contacting Groq: {exc}",
        }

    return {
        "status": "error",
        "model": model,
        "reason": f"LLM error: {type(exc).__name__}: {exc}",
    }


def create_chat_model():
    """Create a low-temperature ChatGroq client from environment settings."""
    is_open, open_reason = is_circuit_open()
    if is_open:
        raise LLMError(f"LLM circuit breaker open ({open_reason}); skipping LLM calls.")

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL")
    if not api_key or not model:
        raise LLMError("GROQ_API_KEY and GROQ_MODEL must be configured")
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        raise LLMError("langchain-groq is not installed") from exc
    return ChatGroq(
        api_key=api_key,
        model=model,
        temperature=0.1,
        timeout=15,
        max_retries=1,
    )
