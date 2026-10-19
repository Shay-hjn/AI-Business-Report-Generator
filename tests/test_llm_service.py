import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from backend.app.services.llm_service import generate_business_report


def sample_analysis():
    """Create verified analytical input for testing."""

    return {
        "monthly_kpis": [
            {
                "month": "2026-08",
                "total_revenue": 10000,
            },
            {
                "month": "2026-09",
                "total_revenue": 12000,
                "revenue_growth_pct": 20,
            },
        ],
        "notable_changes": [
            {
                "type": "overall_revenue_change",
                "absolute_change": 2000,
                "percentage_change": 20,
            }
        ],
    }


def valid_report_json():
    """Create a valid structured LLM response."""

    return json.dumps(
        {
            "executive_summary": ("Revenue increased from 10,000 to 12,000."),
            "key_insights": ["September revenue was 12,000."],
            "notable_changes": ["Revenue increased by 20%."],
        }
    )


def fake_response(content):
    """Simulate a Gemini API response."""

    return SimpleNamespace(text=content)


def test_successful_generation():
    """Valid JSON should succeed on the first attempt."""

    client = Mock()

    client.models.generate_content.return_value = fake_response(valid_report_json())

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert result["ai_report"] is not None

    assert (
        result["ai_report"]["executive_summary"]
        == "Revenue increased from 10,000 to 12,000."
    )

    assert client.models.generate_content.call_count == 1

    # Verify that Gemini is asked for strict structured output
    request = client.models.generate_content.call_args.kwargs

    assert request["config"].response_mime_type == "application/json"
    assert "additionalProperties" not in request["config"].response_schema


def test_retry_after_invalid_json():
    """Invalid JSON should trigger exactly one retry."""

    client = Mock()

    client.models.generate_content.side_effect = [
        fake_response("This is not valid JSON"),
        fake_response(valid_report_json()),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 2

    # Verify that the retry contains validation feedback
    retry_request = client.models.generate_content.call_args_list[1].kwargs

    retry_contents = retry_request["contents"]

    assert "Invalid JSON syntax" in retry_contents

    # The original verified input and system instructions remain
    assert "verified analysis data" in retry_contents
    assert "business analyst" in retry_request["config"].system_instruction.lower()


def test_retry_after_pydantic_validation_error():
    """Missing required fields should trigger a retry."""

    client = Mock()

    invalid_report = json.dumps(
        {
            "executive_summary": "Revenue increased.",
            "key_insights": [],
            # notable_changes is deliberately missing
        }
    )

    client.models.generate_content.side_effect = [
        fake_response(invalid_report),
        fake_response(valid_report_json()),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 2

    retry_request = client.models.generate_content.call_args_list[1].kwargs

    assert "notable_changes" in (retry_request["contents"])


def test_fallback_after_two_invalid_responses():
    """Two validation failures should return a safe fallback."""

    client = Mock()

    client.models.generate_content.side_effect = [
        fake_response("Invalid response one"),
        fake_response("Invalid response two"),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result == {
        "narrative_generated": False,
        "ai_report": None,
    }

    assert client.models.generate_content.call_count == 2


def test_api_failure_fallback():
    """An API connection failure should not crash the application."""

    client = Mock()

    client.models.generate_content.side_effect = ConnectionError("Gemini unavailable")

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result == {
        "narrative_generated": False,
        "ai_report": None,
    }

    # API errors are handled without a validation retry
    assert client.models.generate_content.call_count == 1


def test_unexpected_fields_are_rejected():
    """Pydantic should reject additional JSON fields."""

    client = Mock()

    invalid_report = json.loads(valid_report_json())
    invalid_report["invented_field"] = "Some extra information"

    client.models.generate_content.side_effect = [
        fake_response(json.dumps(invalid_report)),
        fake_response(json.dumps(invalid_report)),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is False
    assert result["ai_report"] is None
    assert client.models.generate_content.call_count == 2


def test_legacy_recommendations_field_is_rejected():
    """Old four-section output is no longer accepted by strict schema."""
    client = Mock()
    old_report = json.loads(valid_report_json())
    old_report["recommendations"] = ["Change pricing immediately."]
    client.models.generate_content.return_value = fake_response(
        json.dumps(old_report)
    )

    result = generate_business_report(sample_analysis(), client=client)

    assert result == {"narrative_generated": False, "ai_report": None}
    assert client.models.generate_content.call_count == 2
