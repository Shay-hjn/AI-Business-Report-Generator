"""Offline checks for attributable segment rankings in the Gemini prompt."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from backend.app.analytics.pipeline import analyze_sales_data

from backend.app.services.llm_service import (
    SYSTEM_PROMPT,
    build_segment_rankings,
    generate_business_report,
)


def three_month_analysis():
    """Mimic the problematic Dataset 09 percentages without an external CSV."""
    return {
        "monthly_kpis": [
            {"month": "2026-06", "total_revenue": 152000},
            {"month": "2026-07", "total_revenue": 154960.65},
            {"month": "2026-08", "total_revenue": 134404.00},
        ],
        "comparisons": [],
        "revenue_breakdowns": {
            "2026-06": {
                "category": {"Electronics": 80000, "Furniture": 60000,
                             "Accessories": 12000},
                "region": {"East": 60000, "West": 92000},
                "product": {},
            },
            "2026-07": {
                "category": {"Electronics": 88805.30, "Furniture": 56170.00,
                             "Accessories": 9985.35},
                "region": {"East": 60000, "West": 94960.65},
                "product": {},
            },
            "2026-08": {
                "category": {"Electronics": 77587.70, "Furniture": 43634.90,
                             "Accessories": 13181.40},
                "region": {"East": 90000, "West": 44404.00},
                "product": {},
            },
        },
        "notable_changes": [],
        "report_highlights": {},
        "top_revenue_product": None,
    }


def fake_response(insight: str):
    return SimpleNamespace(text=json.dumps({
            "executive_summary": "Revenue changed in the reporting period.",
            "key_insights": [insight],
            "notable_changes": [],
        }))


def request_facts(client):
    content = client.models.generate_content.call_args.kwargs["contents"]
    return json.loads(content.split("\n", 1)[1])


def test_latest_rankings_keep_dataset09_category_rates_with_the_right_names():
    rankings = build_segment_rankings(three_month_analysis())
    latest = rankings["latest"]
    assert (latest["from_month"], latest["to_month"]) == ("2026-07", "2026-08")
    assert latest["category"]["largest_eur_decrease"] == [{
        "name": "Furniture", "absolute_change": -12535.10,
        "percentage_change": -22.32,
    }]
    assert latest["category"]["largest_pct_decrease"] == [{
        "name": "Furniture", "absolute_change": -12535.10,
        "percentage_change": -22.32,
    }]
    assert "Electronics" not in [
        event["name"] for event in latest["category"]["largest_pct_decrease"]
    ]
    assert latest["category"]["largest_pct_increase"][0]["name"] == "Accessories"
    assert latest["region"]["largest_eur_decrease"][0]["name"] == "West"


def test_historical_rankings_are_scoped_to_earlier_month_pairs():
    earlier = build_segment_rankings(three_month_analysis())["historical"]
    assert earlier["scope"] == "consecutive_pairs_before_latest"
    assert earlier["category"]["largest_eur_increase"] == [{
        "from_month": "2026-06", "to_month": "2026-07",
        "name": "Electronics", "absolute_change": 8805.30,
        "percentage_change": 11.01,
    }]
    assert earlier["category"]["largest_eur_decrease"] == [{
        "from_month": "2026-06", "to_month": "2026-07",
        "name": "Furniture", "absolute_change": -3830.00,
        "percentage_change": -6.38,
    }]
    assert "2026-08" not in json.dumps(earlier)


def test_rankings_handle_single_month_two_month_zero_baselines_and_ties():
    analysis = {"revenue_breakdowns": {
        "2026-07": {"category": {"A": 0, "B": 10, "C": 10}},
    }}
    assert build_segment_rankings(analysis) == {}
    analysis["revenue_breakdowns"]["2026-08"] = {
        "category": {"A": 10, "B": 20, "C": 20},
    }
    latest = build_segment_rankings(analysis)["latest"]["category"]
    assert latest["largest_eur_increase"] == [
        {"name": "A", "absolute_change": 10, "percentage_change": None},
        {"name": "B", "absolute_change": 10, "percentage_change": 100},
        {"name": "C", "absolute_change": 10, "percentage_change": 100},
    ]
    assert [event["name"] for event in latest["largest_pct_increase"]] == ["B", "C"]
    assert latest["largest_eur_decrease"] == []
    assert latest["largest_pct_decrease"] == []
    assert build_segment_rankings(analysis)["historical"]["category"] == {
        "largest_eur_increase": [], "largest_eur_decrease": [],
    }


def test_request_includes_rankings_and_older_ranked_facts_pass_grounding():
    analysis = three_month_analysis()
    client = Mock()
    client.models.generate_content.return_value = fake_response(
        "Electronics revenue rose by €8,805.30 (11.01%) from June to July."
    )
    result = generate_business_report(analysis, client=client)
    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 1
    payload = request_facts(client)
    assert payload["segment_rankings"]["latest"]["category"]["largest_pct_decrease"][0]["percentage_change"] == -22.32
    assert payload["segment_rankings"]["historical"]["category"]["largest_eur_increase"][0]["percentage_change"] == 11.01
    assert "EARLIER consecutive month pairs" in SYSTEM_PROMPT
    # Unmodified API model and JSON schema contract.
    assert client.models.generate_content.call_args.kwargs["config"].response_mime_type == "application/json"


def test_wrong_latest_segment_percentage_is_not_content_checked():
    client = Mock()
    client.models.generate_content.return_value = fake_response(
        "Furniture revenue fell 12.63% from July to August."
    )
    result = generate_business_report(three_month_analysis(), client=client)
    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 1


@pytest.mark.parametrize("months", [1, 2, 3, 8, 11])
def test_mocked_requests_preserve_reporting_scope_and_payload_compaction(months):
    """Exercise real Python analytics and mocked Gemini across report lengths."""
    rows = []
    for month_index, month in enumerate(
        pd.period_range("2025-10", periods=months, freq="M")
    ):
        for order in range(6):
            price = round((100 + order * 12) * (1 + month_index * 0.12), 2)
            rows.append({
                "order_id": f"{month_index}-{order}",
                "date": f"{month}-12", "customer_id": f"buyer-{order}",
                "product": f"Item {order}",
                "category": "Furniture" if order % 2 else "Electronics",
                "region": "East" if order % 2 else "West",
                "quantity": 1, "unit_price": price, "discount_pct": 0,
                "total_sales": price,
            })
    analysis = analyze_sales_data(pd.DataFrame(rows))
    client = Mock()
    client.models.generate_content.return_value = fake_response(
        "The verified sales figures support comparison across the months."
    )
    assert generate_business_report(analysis, client=client)["narrative_generated"]
    assert client.models.generate_content.call_count == 1
    supplied = request_facts(client)
    if months == 1:
        assert "segment_rankings" not in supplied
    else:
        rankings = supplied["segment_rankings"]
        assert rankings["latest"]["from_month"] == analysis["monthly_kpis"][-2]["month"]
        assert rankings["latest"]["to_month"] == analysis["monthly_kpis"][-1]["month"]
        if months == 2:
            assert rankings["historical"]["category"]["largest_eur_increase"] == []
        else:
            assert rankings["historical"]["category"]["largest_eur_increase"]
    if months >= 3:
        assert len(supplied["verified_analysis"]["revenue_breakdowns"]) == 2
    if months == 11:
        # The added labels stay small enough to preserve payload compaction.
        assert len(json.dumps(supplied, separators=(",", ":"))) < 16000
