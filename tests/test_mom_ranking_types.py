"""Absolute EUR and percentage MoM rankings must stay distinct."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from backend.app.analytics.metrics import (
    calculate_monthly_comparisons,
    calculate_monthly_kpis,
    calculate_report_highlights,
)
from backend.app.services.llm_service import SYSTEM_PROMPT, generate_business_report


def highlights_for(revenues):
    sales = pd.DataFrame([
        {"order_id": f"O-{month}", "date": f"{month}-15",
         "product": "Office Desk", "quantity": 1, "total_sales": revenue}
        for month, revenue in revenues
    ])
    monthly = calculate_monthly_kpis(sales)
    comparisons = calculate_monthly_comparisons(monthly)
    return calculate_report_highlights(sales, monthly, comparisons)


def test_absolute_and_percentage_extremes_are_different():
    facts = highlights_for([
        ("2026-01", 1000), ("2026-02", 400),
        ("2026-03", 410), ("2026-04", 100),
        ("2026-05", 250), ("2026-06", 600),
    ])
    assert facts["largest_monthly_revenue_increase"]["from_month"] == "2026-05"
    assert facts["largest_monthly_revenue_increase"]["to_month"] == "2026-06"
    assert facts["largest_monthly_revenue_increase"]["absolute_change"] == 350
    assert facts["largest_monthly_revenue_percentage_increase"]["from_month"] == "2026-04"
    assert facts["largest_monthly_revenue_percentage_increase"]["to_month"] == "2026-05"
    assert facts["largest_monthly_revenue_percentage_increase"]["percentage_change"] == 150

    assert facts["largest_monthly_revenue_decrease"]["to_month"] == "2026-02"
    assert facts["largest_monthly_revenue_decrease"]["absolute_change"] == -600
    assert facts["largest_monthly_revenue_percentage_decrease"]["to_month"] == "2026-04"
    assert facts["largest_monthly_revenue_percentage_decrease"]["percentage_change"] == -75.61


def test_one_and_two_month_cases_keep_historical_rankings_unavailable():
    one = highlights_for([("2026-01", 100)])
    two = highlights_for([("2026-01", 100), ("2026-02", 120)])
    for facts in (one, two):
        assert facts["largest_monthly_revenue_percentage_increase"] is None
        assert facts["largest_monthly_revenue_percentage_decrease"] is None
    assert two["overall_revenue_change"]["percentage_change"] == 20


def test_zero_previous_revenue_not_used_for_percentage_ranking():
    facts = highlights_for([
        ("2026-01", 0), ("2026-02", 100),
        ("2026-03", 200), ("2026-04", 100),
    ])
    assert facts["largest_monthly_revenue_increase"]["from_month"] == "2026-01"
    assert facts["largest_monthly_revenue_increase"]["percentage_change"] is None
    assert facts["largest_monthly_revenue_percentage_increase"]["from_month"] == "2026-02"
    assert facts["largest_monthly_revenue_percentage_increase"]["percentage_change"] == 100


def test_no_positive_or_negative_change_returns_none():
    falling = highlights_for([
        ("2026-01", 300), ("2026-02", 200), ("2026-03", 100)
    ])
    rising = highlights_for([
        ("2026-01", 100), ("2026-02", 200), ("2026-03", 300)
    ])
    assert falling["largest_monthly_revenue_increase"] is None
    assert falling["largest_monthly_revenue_percentage_increase"] is None
    assert rising["largest_monthly_revenue_decrease"] is None
    assert rising["largest_monthly_revenue_percentage_decrease"] is None


def test_gemini_receives_both_rankings_without_required_coverage_validation():
    facts = highlights_for([
        ("2026-01", 1000), ("2026-02", 400),
        ("2026-03", 410), ("2026-04", 100),
        ("2026-05", 250), ("2026-06", 600),
    ])
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=json.dumps({
            "executive_summary": "Revenue changed across the six-month period.",
            "key_insights": ["The latest month recovered."],
            "notable_changes": [],
        }))
    analysis = {
        "monthly_kpis": [], "notable_changes": [], "report_highlights": facts
    }
    result = generate_business_report(analysis, client=client)
    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 1
    prompt = client.models.generate_content.call_args.kwargs["contents"]
    payload = json.loads(prompt.split("\n", 1)[1])
    assert payload["verified_analysis"]["report_highlights"] == facts
    assert "ABSOLUTE" in payload["metric_definitions"]["report_highlights.largest_monthly_revenue_increase"]
    assert "PERCENTAGE" in payload["metric_definitions"]["report_highlights.largest_monthly_revenue_percentage_increase"]
    assert "month pairs may differ" in SYSTEM_PROMPT
