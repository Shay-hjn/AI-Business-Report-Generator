import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


# Load environment variables from .env
project_root = Path(__file__).resolve().parents[1]
load_dotenv(project_root / ".env")

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("LLM_MODEL")

if not api_key or not model:
    raise SystemExit("Missing GROQ_API_KEY or LLM_MODEL in .env")

try:
    # Connect to Groq
    client = Groq(
        api_key=api_key,
        timeout=30.0,
        max_retries=0,
    )

    # Send a simple request to the LLM
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": "Reply briefly: Is this API connection working?",
            }
        ],
        max_completion_tokens=300,
    )

    # Display the response
    print("Model:", model)
    print("LLM response:", response.choices[0].message.content)

except Exception as error:
    print(f"API request failed: {type(error).__name__}")

    status_code = getattr(error, "status_code", None)

    if status_code is not None:
        print("HTTP status:", status_code)
