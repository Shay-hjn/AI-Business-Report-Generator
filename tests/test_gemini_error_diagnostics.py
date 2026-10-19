"""No-live-call regression tests for sanitized Gemini error diagnostics."""

import logging

from backend.app.services import llm_service


def test_gemini_400_logs_provider_message_without_exposing_key(monkeypatch, caplog):
    secret = "TEST_SECRET_SHOULD_NOT_APPEAR_12345"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    class InvalidArgument(Exception):
        code = 400
        message = f"Invalid response schema for supplied JSON. api_key={secret}"

    class FailingProvider:
        name = "gemini"

        def generate(self, *_args, **_kwargs):
            raise InvalidArgument()

    monkeypatch.setattr(llm_service, "make_provider", lambda *args, **kwargs: FailingProvider())
    with caplog.at_level(logging.ERROR, logger=llm_service.__name__):
        result = llm_service.generate_business_report({"monthly_kpis": []}, client=object())

    assert result == {"narrative_generated": False, "ai_report": None}
    assert "HTTP status: 400" in caplog.text
    assert "Invalid response schema" in caplog.text
    assert secret not in caplog.text
    assert "[redacted]" in caplog.text


def test_organization_ids_remain_redacted():
    error = Exception()
    error.message = "Limit reached in org_testOrgId: please wait"
    assert "org_testOrgId" not in llm_service._safe_api_error_detail(error)


def test_manual_gemini_model_selection(monkeypatch):
    """An alternative model is selected only when LLM_MODEL changes."""
    from backend.app.services.llm_providers import read_llm_settings

    monkeypatch.setenv("GEMINI_API_KEY", "testing-only")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash-lite")
    settings = read_llm_settings()
    assert settings.provider == "gemini"
    assert settings.model == "gemini-3.5-flash-lite"
    assert settings.retry_content_validation is True  # Test fixture explicitly enables this.


def test_unsupported_llm_provider_is_rejected(monkeypatch):
    """The application exposes only the Gemini integration."""
    import pytest
    from backend.app.services.llm_providers import read_llm_settings

    monkeypatch.setenv("LLM_PROVIDER", "unsupported-service")
    monkeypatch.setenv("GEMINI_API_KEY", "testing-only")
    with pytest.raises(ValueError, match="LLM_PROVIDER must be 'gemini'"):
        read_llm_settings()


def test_gemini_503_falls_back_without_repeated_requests():
    """An overloaded API must not trigger automatic model or HTTP retry."""
    from unittest.mock import Mock

    from backend.app.services.llm_service import generate_business_report

    error = Exception("Temporary service overload")
    error.code = 503
    error.message = "This model is currently experiencing high demand."
    client = Mock()
    client.models.generate_content.side_effect = error
    result = generate_business_report({"monthly_kpis": []}, client=client)
    assert result == {"narrative_generated": False, "ai_report": None}
    client.models.generate_content.assert_called_once()
