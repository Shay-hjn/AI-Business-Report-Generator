"""Conservative context-aware validation of segment percentage statements.

Run with: python -m pytest tests/test_llm_attribution.py -q
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.schemas import BusinessReport
from backend.app.services.llm_service import (
    SYSTEM_PROMPT,
    build_latest_segment_comparisons,
    check_segment_percentage_attribution,
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


def report(insight):
    return BusinessReport(
        executive_summary="Revenue decreased in August.",
        key_insights=[insight], notable_changes=[],
    )


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


def test_detects_wrong_region_rate_even_when_number_is_verified_elsewhere():
    errors = check_segment_percentage_attribution(
        report("East revenue fell 35.55% from July to Aug, "
               "North fell 35.55%, while West rose 62.27% in the same interval."),
        analysis(),
    )
    assert len(errors) == 1
    assert "East" in errors[0]
    assert "33.84%" in errors[0]


def test_correct_region_rates_pass():
    errors = check_segment_percentage_attribution(
        report("East revenue fell 33.84% from July to Aug, "
               "North fell 35.55%, while West rose 62.27% in the same interval."),
        analysis(),
    )
    assert errors == []


def test_detects_direction_mismatch_with_correct_number():
    errors = check_segment_percentage_attribution(
        report("East revenue rose 33.84% from July to August."), analysis(),
    )
    assert errors and "East" in errors[0]


def test_explicit_historical_period_is_not_confused_with_latest():
    history = analysis()
    history["revenue_breakdowns"] = {
        "2026-05": {"region": {"East": 100, "North": 100}},
        "2026-06": {"region": {"East": 150, "North": 100}},
        "2026-07": {"region": {"East": 100, "North": 50}},
    }
    assert check_segment_percentage_attribution(
        report("East revenue rose 50% from May to June 2026."), history,
    ) == []
    errors = check_segment_percentage_attribution(
        report("East revenue declined 50% from June to July 2026."), history,
    )
    assert len(errors) == 1
    assert "33.33%" in errors[0]


def test_ambiguous_period_skipped_not_false_rejected():
    assert check_segment_percentage_attribution(
        report("East revenue declined 35.55% during the year."),
        {**analysis(), "revenue_breakdowns": {
            **analysis()["revenue_breakdowns"],
            "2026-06": {"region": {"East": 30000}},
        }},
    ) == []


def test_single_month_uses_no_prior_period():
    one = {"revenue_breakdowns": {"2026-08": {
        "region": {"East": 200}, "category": {"Office": 200},
    }}}
    assert build_latest_segment_comparisons(one)["from_month"] is None
    assert check_segment_percentage_attribution(
        report("East revenue rose 25% in August."), one,
    ) == []


def test_validation_retries_one_wrong_attribution_and_preserves_ai_freedom():
    client = Mock()
    client.models.generate_content.side_effect = [
        fake_response("East revenue fell 35.55% from July to August."),
        fake_response("East revenue fell 33.84% from July to August."),
    ]
    result = generate_business_report(analysis(), client=client)
    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 2
    assert "East" in client.models.generate_content.call_args_list[1].kwargs["contents"]
    payload = json.loads(client.models.generate_content.call_args_list[0].kwargs["contents"].split("\n", 1)[1])
    assert payload["latest_segment_comparisons"]["region"]["East"]["percentage_change"] == -33.84
    assert "lowest" in SYSTEM_PROMPT.lower()


def test_report_with_no_required_high_low_mentions_is_still_accepted():
    client = Mock()
    client.models.generate_content.return_value = fake_response(
        "Electronics revenue was lower in August."
    )
    assert generate_business_report(analysis(), client=client)["narrative_generated"]
    assert client.models.generate_content.call_count == 1
