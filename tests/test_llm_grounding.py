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


def test_wrong_currency_is_retried():
    """Incorrect currency should trigger exactly one retry."""

    client = Mock()

    client.models.generate_content.side_effect = [
        fake_response(report_json(summary="Revenue was $100.")),
        fake_response(report_json(summary="Revenue was €100.")),
    ]

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 2

    retry_request = client.models.generate_content.call_args_list[1].kwargs

    feedback = retry_request["contents"]

    assert "Unsupported currency" in feedback


def test_wrong_currency_twice_uses_fallback():
    """Two wrong-currency responses should trigger fallback."""

    client = Mock()

    client.models.generate_content.return_value = fake_response(
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

    assert client.models.generate_content.call_count == 2


def test_top_selling_terminology_is_retried():
    """Revenue ranking must not be confused with units sold."""

    client = Mock()

    client.models.generate_content.side_effect = [
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
    assert client.models.generate_content.call_count == 2

    assert result["ai_report"]["key_insights"] == [
        "The highest-revenue product was Office Desk."
    ]


def test_top_selling_twice_uses_fallback():
    """Repeated incorrect terminology must trigger fallback."""

    client = Mock()

    client.models.generate_content.return_value = fake_response(
        report_json(insight="The best-selling product was Office Desk.")
    )

    result = generate_business_report(
        sample_analysis(),
        client=client,
    )

    assert result["narrative_generated"] is False
    assert result["ai_report"] is None
    assert client.models.generate_content.call_count == 2


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
        "top_product_by_units_full_period": {
            "product": "Office Desk",
            "units_sold": 90,
        },
        "top_product_by_revenue_full_period": {
            "product": "Office Desk",
            "revenue": 120,
        },
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


def test_verified_unit_rank_is_allowed_but_best_selling_is_not():
    from backend.app.services.llm_service import has_unsupported_product_ranking
    from backend.app.schemas import BusinessReport

    report = BusinessReport.model_validate(
        json.loads(
            report_json(
                insight="Office Desk had the most units sold over the full reporting period."
            )
        )
    )
    assert has_unsupported_product_ranking(report, sample_analysis())
    known = sample_analysis()
    known["report_highlights"] = {
        "top_product_by_units_full_period": {"product": "Office Desk", "units_sold": 90}
    }
    assert not has_unsupported_product_ranking(report, known)
    report2 = BusinessReport.model_validate(
        json.loads(report_json(insight="Office Desk is the best-selling product."))
    )
    assert has_unsupported_product_ranking(report2, known)


def test_unverified_euro_amount_is_retried():
    client = Mock()
    client.models.generate_content.side_effect = [
        fake_response(report_json(insight="Revenue rose to €999.00.")),
        fake_response(report_json(insight="Revenue was €100.00.")),
    ]
    result = generate_business_report(sample_analysis(), client=client)
    assert result["narrative_generated"]
    assert client.models.generate_content.call_count == 2
    feedback = client.models.generate_content.call_args_list[1].kwargs["contents"]
    assert "Unverified EUR amount" in feedback


def test_unsupported_efficiency_claim_is_retried():
    client = Mock()
    client.models.generate_content.side_effect = [
        fake_response(
            report_json(
                insight="Revenue per unit rose, reflecting improved efficiency."
            )
        ),
        fake_response(report_json(insight="Revenue per unit rose.")),
    ]
    result = generate_business_report(sample_analysis(), client=client)
    assert result["narrative_generated"]
    assert client.models.generate_content.call_count == 2
    feedback = client.models.generate_content.call_args_list[1].kwargs["contents"]
    assert "Unsupported causal explanation" in feedback


def test_bad_percent_retried_but_rounded_verified_percent_allowed():
    client = Mock()
    analysis = sample_analysis()
    analysis["monthly_kpis"][-1]["revenue_growth_pct"] = 43.74
    client.models.generate_content.side_effect = [
        fake_response(report_json(insight="Revenue increased 75%.")),
        fake_response(report_json(insight="Revenue increased roughly 44%.")),
    ]
    result = generate_business_report(analysis, client=client)
    assert result["narrative_generated"]
    assert client.models.generate_content.call_count == 2


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
