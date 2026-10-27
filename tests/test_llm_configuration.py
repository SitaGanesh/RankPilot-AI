"""Tests for LLM configuration, circuit breaker, and startup validation."""

import os
import pytest
from core.errors import LLMError
from core.llm import (
    create_chat_model,
    is_circuit_open,
    is_permanent_error,
    log_llm_failure_once_per_audit,
    reset_circuit_breaker,
    trip_circuit_breaker,
    validate_llm_config,
)


@pytest.fixture(autouse=True)
def clean_circuit():
    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


def test_circuit_breaker_trips_and_blocks_create_chat_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    open_state, reason = is_circuit_open()
    assert open_state is False

    trip_circuit_breaker("model_not_found")
    open_state, reason = is_circuit_open()
    assert open_state is True
    assert reason == "model_not_found"

    with pytest.raises(LLMError, match="circuit breaker open"):
        create_chat_model()


def test_circuit_breaker_reset():
    trip_circuit_breaker("404 error")
    assert is_circuit_open()[0] is True
    reset_circuit_breaker()
    assert is_circuit_open()[0] is False


def test_is_permanent_error_classification():
    class MockHttpError(Exception):
        status_code = 404

    class MockAuthError(Exception):
        pass
    MockAuthError.__name__ = "AuthenticationError"

    assert is_permanent_error(MockHttpError("Not Found")) is True
    assert is_permanent_error(MockAuthError("Unauthorized")) is True
    assert is_permanent_error(Exception("The model `xyz` does not exist or you do not have access")) is True
    assert is_permanent_error(Exception("Connection timed out")) is False


def test_validate_llm_config_missing_env(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    res = validate_llm_config(force_refresh=True)
    assert res["status"] == "not_configured"
    assert "GROQ_API_KEY" in res["reason"]


def test_validate_llm_config_never_exposes_api_key(monkeypatch):
    secret_key = "gsk_super_secret_unique_key_12345"
    monkeypatch.setenv("GROQ_API_KEY", secret_key)
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    res = validate_llm_config(force_refresh=True)
    res_str = str(res)
    assert secret_key not in res_str


def test_log_llm_failure_once_per_audit(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        log_llm_failure_once_per_audit("audit-123", "LLM failed once")
        log_llm_failure_once_per_audit("audit-123", "LLM failed twice")
        log_llm_failure_once_per_audit("audit-123", "LLM failed thrice")

    messages = [rec.message for rec in caplog.records if "LLM failed" in rec.message]
    assert len(messages) == 1
