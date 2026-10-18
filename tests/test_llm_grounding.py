import json
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.services.llm_service import (
    build_segment_directions,
    generate_business_report,
    normalize_text_spacing,
)


def sample_analysis():
    """Create verified data with mixed segment performance."""

    return {
        "monthly_kpis": [
            {"month": "2026-08", "total_revenue": 100},
            {"month": "2026-09", "total_revenue": 100},
        ],
        "revenue_breakdowns": {
            "2026-08": {
                "category": {
                    "Electronics": 70,
                    "Furniture": 20,
                    "Accessories": 10,
                },
                "region": {
                    "North": 60,
                    "South": 40,
                },
            },
            "2026-09": {
                "category": {
                    "Electronics": 30,
                    "Furniture": 60,
                    "Accessories": 10,
                },
                "region": {
                    "North": 10,
                    "South": 90,
                },
            },
        },
        "notable_changes": [],
        "top_revenue_product": {
            "product": "Office Desk",
            "revenue": 40,
            "month": "2026-09",
        },
    }


def fake_response(content):
    """Simulate a response from the Groq API."""

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def report_json(
    summary="Total revenue remained at €100.",
    insight="Category performance was mixed.",
):
    """Create a valid AI report for testing."""

    return json.dumps(
        {
            "executive_summary": summary,
            "key_insights": [insight],
            "notable_changes": ["North region revenue decreased."],
            "recommendations": ["Investigate regional changes."],
        }
    )


def test_segment_directions():
    """Python must correctly identify segment trends."""

    directions = build_segment_directions(sample_analysis())

    assert directions["category"] == {
        "Accessories": "unchanged",
        "Electronics": "decreased",
        "Furniture": "increased",
    }

    assert directions["region"] == {
        "North": "decreased",
        "South": "increased",
    }


def test_eur_and_metric_definitions_are_sent():
    """Verify the configuration and facts sent to the LLM."""

    client = Mock()

    client.chat.completions.create.return_value = fake_response(report_json())

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True

    request = client.chat.completions.create.call_args.kwargs

    # Verify our current model configuration.
    assert request["reasoning_effort"] == "medium"
    assert request["max_completion_tokens"] == 2000

    user_message = request["messages"][1]["content"]

    supplied_data = json.loads(user_message.split("\n", 1)[1])

    assert supplied_data["currency"] == "EUR"
    assert supplied_data["currency_symbol"] == "€"

    assert (
        "highest total revenue"
        in (supplied_data["metric_definitions"]["top_revenue_product"])
    )

    assert supplied_data["latest_segment_directions"] == (
        build_segment_directions(sample_analysis())
    )


def test_euro_symbol_is_allowed():
    """Correct currency must not trigger a retry."""

    client = Mock()

    client.chat.completions.create.return_value = fake_response(report_json())

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.chat.completions.create.call_count == 1


def test_wrong_currency_is_retried():
    """Incorrect currency should trigger exactly one retry."""

    client = Mock()

    client.chat.completions.create.side_effect = [
        fake_response(report_json(summary="Revenue was $100.")),
        fake_response(report_json(summary="Revenue was €100.")),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.chat.completions.create.call_count == 2

    retry_request = client.chat.completions.create.call_args_list[1].kwargs

    feedback = retry_request["messages"][-1]["content"]

    assert "Unsupported currency" in feedback


def test_wrong_currency_twice_uses_fallback():
    """Two wrong-currency responses should trigger fallback."""

    client = Mock()

    client.chat.completions.create.return_value = fake_response(
        report_json(summary="Revenue was £100.")
    )

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result == {
        "narrative_generated": False,
        "ai_report": None,
    }

    assert client.chat.completions.create.call_count == 2


def test_top_selling_terminology_is_retried():
    """Revenue ranking must not be confused with units sold."""

    client = Mock()

    client.chat.completions.create.side_effect = [
        fake_response(report_json(insight="The top-selling product was Office Desk.")),
        fake_response(
            report_json(insight=("The highest-revenue product was Office Desk."))
        ),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.chat.completions.create.call_count == 2

    assert result["ai_report"]["key_insights"] == [
        "The highest-revenue product was Office Desk."
    ]


def test_top_selling_twice_uses_fallback():
    """Repeated incorrect terminology must trigger fallback."""

    client = Mock()

    client.chat.completions.create.return_value = fake_response(
        report_json(insight="The best-selling product was Office Desk.")
    )

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is False
    assert result["ai_report"] is None
    assert client.chat.completions.create.call_count == 2


def test_spacing_normalization():
    """Fix missing spaces after punctuation and percentages."""

    text = (
        "Revenue increased,whereas orders decreased.North revenue fell by 85%decrease."
    )

    corrected = normalize_text_spacing(text)

    assert "increased, whereas" in corrected
    assert "decreased. North" in corrected
    assert "85% decrease" in corrected


def test_spacing_normalization_preserves_numbers():
    """Formatting corrections must preserve monetary values."""

    text = "Revenue was €140,954.75(-54.08%)."

    corrected = normalize_text_spacing(text)

    assert corrected == "Revenue was €140,954.75 (-54.08%)."


def test_report_spacing_is_corrected_automatically():
    """The returned report should have corrected spacing."""

    client = Mock()

    client.chat.completions.create.return_value = fake_response(
        report_json(summary=("Revenue was €100,whereas orders were stable."))
    )

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True

    assert result["ai_report"]["executive_summary"] == (
        "Revenue was €100.00, whereas orders were stable."
    )

    assert client.chat.completions.create.call_count == 1
