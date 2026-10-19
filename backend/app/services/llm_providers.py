"""Gemini integration and LLM configuration for structured reports.

API calls occur only during report generation, never on import.
"""

import os
from dataclasses import dataclass

from backend.app.schemas import BusinessReport


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str
    max_output_tokens: int
    thinking_level: str
    retry_content_validation: bool


def read_llm_settings() -> LLMSettings:
    """Read Gemini settings. Switch models manually via LLM_MODEL in .env."""
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider != "gemini":
        raise ValueError("LLM_PROVIDER must be 'gemini'.")
    model = os.getenv("LLM_MODEL", "").strip() or "gemini-3.8-flash"
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    try:
        tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "6000"))
    except ValueError as exc:
        raise ValueError("LLM_MAX_OUTPUT_TOKENS must be an integer.") from exc
    if not 256 <= tokens <= 65536:
        raise ValueError("LLM_MAX_OUTPUT_TOKENS must be between 256 and 65536.")

    level = os.getenv("LLM_THINKING_LEVEL", "medium").strip().lower()
    if level not in {"low", "medium", "high"}:
        raise ValueError("LLM_THINKING_LEVEL must be low, medium, or high.")
    retry = os.getenv("LLM_RETRY_CONTENT_VALIDATION", "0").strip().lower()
    return LLMSettings(
        provider=provider, model=model, api_key=key,
        max_output_tokens=tokens, thinking_level=level,
        retry_content_validation=retry not in {"0", "false", "no", "off"},
    )


class GeminiProvider:
    name = "gemini"

    def __init__(self, key: str | None = None, client=None):
        if client is None:
            from google import genai
            client = genai.Client(api_key=key, http_options={"timeout": 60000})
        self.client = client

    def generate(self, messages: list[dict], model: str, *,
                 max_output_tokens: int = 6000,
                 thinking_level: str = "medium") -> str:
        """Request structured JSON; the report is also validated locally."""
        from google.genai import types

        system = "\n".join(msg["content"] for msg in messages if msg["role"] == "system")
        user = "\n\n".join(msg["content"] for msg in messages if msg["role"] == "user")
        # Gemini rejects Pydantic's `additionalProperties` schema hint.
        # Keep the local Pydantic extra="forbid" validation unchanged.
        response_schema = BusinessReport.model_json_schema()
        response_schema.pop("additionalProperties", None)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=response_schema,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        )
        response = self.client.models.generate_content(
            model=model, contents=user, config=config,
        )
        return response.text or ""


def make_provider(settings: LLMSettings, client=None) -> GeminiProvider:
    return GeminiProvider(settings.api_key, client=client)
