"""Isolate model configuration so offline tests never use a live API key."""

import pytest


@pytest.fixture(autouse=True)
def isolate_llm_configuration(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("LLM_RETRY_CONTENT_VALIDATION", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("LLM_THINKING_LEVEL", raising=False)
