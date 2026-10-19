"""Checks model input facts and the deliberate absence of prose fact-checking."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.services.llm_service import (
    SYSTEM_PROMPT,
    build_latest_segment_comparisons,
    generate_business_report,
)


def analysis():
    """Regions have different changes, including one valid rate for another."""
    return {
        "monthly_kpis": [
            {"month": "2026-07", "total_revenue": 154960.65},
            {"month": "2026-08", "total_revenue": 134404.00,
             "revenue_growth_pct": -13.27},
        ],
        "comparisons": [
            {"from_month": "2026-07", "to_month": "2026-08", "changes": {
                "total_revenue": {
                    "absolute_change": -20556.65,
                    "percentage_change": -13.27,
                },
            }},
        ],
        "revenue_breakdowns": {
            "2026-07": {
                "region": {"East": 40400.20, "North": 49305.80,
                           "West": 25300.10},
                "category": {"Electronics": 88805.30, "Accessories": 9985.35},
            },
            "2026-08": {
                "region": {"East": 26728.30, "North": 31778.35,
                           "West": 41055.20},
                "category": {"Electronics": 77587.70, "Accessories": 13181.40},
            },
        },
        "notable_changes": [],
    }




def fake_response(content):
    return SimpleNamespace(text=json.dumps({
            "executive_summary": "Revenue decreased in August.",
            "key_insights": [content], "notable_changes": [],
        }))


def test_python_provides_attributed_latest_period_facts():
    facts = build_latest_segment_comparisons(analysis())
    assert facts["from_month"] == "2026-07"
    assert facts["to_month"] == "2026-08"
    assert facts["region"]["East"]["percentage_change"] == -33.84
    assert facts["region"]["North"]["percentage_change"] == -35.55
    assert facts["region"]["West"]["percentage_change"] == 62.27
    assert facts["category"]["Electronics"]["percentage_change"] == -12.63












def test_single_month_uses_no_prior_period():
    one = {"revenue_breakdowns": {"2026-08": {
        "region": {"East": 200}, "category": {"Office": 200},
    }}}
    assert build_latest_segment_comparisons(one)["from_month"] is None




def test_report_with_no_required_high_low_mentions_is_still_accepted():
    client = Mock()
    client.models.generate_content.return_value = fake_response(
        "Electronics revenue was lower in August."
    )
    assert generate_business_report(analysis(), client=client)["narrative_generated"]
    assert client.models.generate_content.call_count == 1


def test_incorrect_natural_language_claim_is_no_longer_rejected():
    """The trade-off: JSON is valid even if a narrative claim is inaccurate."""
    client = Mock()
    client.models.generate_content.return_value = fake_response(
        "East revenue fell 35.55% from July to August."  # actual: 33.84%
    )
    result = generate_business_report(analysis(), client=client)
    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 1
    assert "35.55%" in result["ai_report"]["key_insights"][0]
