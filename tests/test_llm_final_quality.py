import json
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.services.llm_service import (
    SYSTEM_PROMPT,
    generate_business_report,
    normalize_text_spacing,
)


def sample_analysis():
    return {
        "monthly_kpis": [
            {"month": "2026-08", "total_revenue": 84380.00},
            {"month": "2026-09", "total_revenue": 57920.70},
        ],
        "revenue_breakdowns": {},
        "notable_changes": [],
    }


def fake_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def report_json(insight):
    return json.dumps(
        {
            "executive_summary": "Revenue decreased by €26,459.3.",
            "key_insights": [insight],
            "notable_changes": ["Revenue was €84,380.0, then €57,920.7."],
        }
    )


def test_currency_values_have_two_decimals_and_thousands_separators():
    assert normalize_text_spacing("€100, €14607.3, €57,920.7") == (
        "€100.00, €14,607.30, €57,920.70"
    )


def test_negative_currency_sign_is_before_euro_symbol():
    assert normalize_text_spacing("€-26,459.3; €‑100; €−5.6") == (
        "-€26,459.30; -€100.00; -€5.60"
    )


def test_percentages_and_nonmonetary_values_are_unchanged():
    assert normalize_text_spacing("Down 31.36% (280 orders), -€25.50.") == (
        "Down 31.36% (280 orders), -€25.50."
    )


def test_prompt_explicitly_rules_out_unverified_price_explanations():
    assert "Never infer a shift toward lower-priced items" in SYSTEM_PROMPT
    assert "by themselves, establish lower selling prices" in SYSTEM_PROMPT


def test_unsupported_price_inference_gets_one_retry():
    client = Mock()
    client.chat.completions.create.side_effect = [
        fake_response(
            report_json(
                "Revenue per unit declined, indicating a shift toward lower-priced items."
            )
        ),
        fake_response(
            report_json("Revenue per unit declined while units sold increased.")
        ),
    ]

    result = generate_business_report(sample_analysis(), client=client)

    assert result["narrative_generated"] is True
    assert client.chat.completions.create.call_count == 2
    assert result["ai_report"]["key_insights"] == [
        "Revenue per unit declined while units sold increased."
    ]
    feedback = client.chat.completions.create.call_args_list[1].kwargs["messages"][-1][
        "content"
    ]
    assert "Unsupported price explanation" in feedback


def test_price_inference_twice_returns_fallback():
    client = Mock()
    client.chat.completions.create.return_value = fake_response(
        report_json("Revenue per unit declined, suggesting lower-priced products.")
    )

    result = generate_business_report(sample_analysis(), client=client)

    assert result == {"narrative_generated": False, "ai_report": None}
    assert client.chat.completions.create.call_count == 2


def test_final_report_formats_euro_values_in_all_sections():
    client = Mock()
    client.chat.completions.create.return_value = fake_response(
        report_json("The change was €‑26,459.3,and volume increased.")
    )

    result = generate_business_report(sample_analysis(), client=client)

    assert result["narrative_generated"] is True
    assert result["ai_report"]["executive_summary"] == (
        "Revenue decreased by €26,459.30."
    )
    assert result["ai_report"]["key_insights"] == [
        "The change was -€26,459.30, and volume increased."
    ]
    assert result["ai_report"]["notable_changes"] == [
        "Revenue was €84,380.00, then €57,920.70."
    ]
    assert client.chat.completions.create.call_count == 1
