"""Optional Gemini connection check (makes one request and consumes quota)."""
from pathlib import Path

from dotenv import load_dotenv

from backend.app.services.llm_providers import make_provider, read_llm_settings


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    settings = read_llm_settings()
    provider = make_provider(settings)
    print("Provider:", settings.provider, "Model:", settings.model)
    answer = provider.generate(
        [
            {"role": "system", "content": "Give a short response."},
            {"role": "user", "content": "Reply with a three-section JSON business report using empty lists and the text 'Connection OK' in executive_summary."},
        ],
        settings.model,
        max_output_tokens=settings.max_output_tokens,
        thinking_level=settings.thinking_level,
    )
    print("Model reply:", answer)


if __name__ == "__main__":
    main()
