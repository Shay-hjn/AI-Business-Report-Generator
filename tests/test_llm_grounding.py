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
    """Simulate a response from the Gemini API."""

    return SimpleNamespace(text=content)


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

    client.models.generate_content.return_value = fake_response(report_json())

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True

    request = client.models.generate_content.call_args.kwargs

    # Verify our current model configuration.
    level = request["config"].thinking_config.thinking_level
    assert str(getattr(level, "value", level)).lower() == "medium"
    assert request["config"].max_output_tokens == 6000

    user_message = request["contents"]

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

    client.models.generate_content.return_value = fake_response(report_json())

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 1










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

    client.models.generate_content.return_value = fake_response(
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

    assert client.models.generate_content.call_count == 1


def test_multi_month_scope_and_product_rankings_are_passed_to_gemini():
    from backend.app.services.llm_service import SYSTEM_PROMPT
    client = Mock()
    analysis = sample_analysis()
    analysis["report_highlights"] = {
        "month_count": 3,
        "top_product_by_units_full_period": {"product": "Office Desk", "units_sold": 90},
        "top_product_by_revenue_full_period": {"product": "Office Desk", "revenue": 120},
    }
    analysis["monthly_kpis"].append({"month": "2026-10", "total_revenue": 120})
    client.models.generate_content.return_value = fake_response(report_json())
    assert generate_business_report(analysis, client=client)["narrative_generated"]
    payload = client.models.generate_content.call_args.kwargs["contents"]
    supplied = json.loads(payload.split("\n", 1)[1])
    assert supplied["reporting_scope"] == "three_or_more_months"
    assert supplied["verified_analysis"]["report_highlights"]["month_count"] == 3
    assert "ONE MONTH" in SYSTEM_PROMPT
    assert "TWO MONTHS" in SYSTEM_PROMPT
    assert "THREE OR MORE MONTHS" in SYSTEM_PROMPT










def test_no_mandatory_coverage_validation_is_added():
    """Intentional product choice: rely on prompt + scenario review for coverage."""
    client = Mock()
    analysis = sample_analysis()
    analysis["report_highlights"] = {
        "month_count": 8,
        "highest_revenue_month": {"months": ["2026-06"], "revenue": 500},
        "lowest_revenue_month": {"months": ["2026-01"], "revenue": 10},
    }
    client.models.generate_content.return_value = fake_response(report_json())
    result = generate_business_report(analysis, client=client)
    assert result["narrative_generated"]
    assert client.models.generate_content.call_count == 1


def test_decline_display_removes_redundant_negative_euro_sign():
    from backend.app.services.llm_service import normalize_text_spacing
    result = normalize_text_spacing(
        "Revenue declined by -€26,459.3; an absolute decrease of -€100.00."
    )
    assert result == (
        "Revenue declined by €26,459.30; an absolute decrease of €100.00."
    )


def test_decline_display_removes_parenthesized_redundant_minus():
    from backend.app.services.llm_service import normalize_text_spacing
    assert normalize_text_spacing("Revenue declined by -€100 (-10%).") == (
        "Revenue declined by €100.00 (10%)."
    )
