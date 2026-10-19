"""Single-month LLM grounding rules with mocked Gemini output."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.services.llm_service import (
    SYSTEM_PROMPT,
    generate_business_report,
    has_unsupported_price_inference,
)
from backend.app.schemas import BusinessReport


def _answer(summary):
    report = {
        "executive_summary": summary,
        "key_insights": ["Electronics had the largest category revenue."],
        "notable_changes": [],
    }
    return SimpleNamespace(text=json.dumps(report))


def test_single_month_prompt_excludes_unverified_pricing_mix():
    assert "For single-month reports" in SYSTEM_PROMPT
    report = BusinessReport(
        executive_summary="Revenue per unit was €472.38, reflecting the pricing mix.",
        key_insights=[], notable_changes=[],
    )
    assert has_unsupported_price_inference(report) is True


def test_single_month_llm_retries_unverified_pricing_mix():
    analysis = {
        "monthly_kpis": [{
            "month": "2026-08", "total_revenue": 109592.90,
            "order_count": 168, "units_sold": 232,
            "average_order_value": 652.34,
            "revenue_per_unit": 472.38,
            "revenue_growth_pct": None,
        }],
        "revenue_breakdowns": {"2026-08": {
            "category": {"Electronics": 109592.90},
            "region": {"North": 109592.90},
        }},
        "notable_changes": [],
    }
    client = Mock()
    client.models.generate_content.side_effect = [
        _answer("Revenue per unit was €472.38, reflecting the pricing mix."),
        _answer("Revenue per unit was €472.38 in August 2026."),
    ]
    result = generate_business_report(analysis, client=client)
    assert result["narrative_generated"] is True
    assert client.models.generate_content.call_count == 2
    assert result["ai_report"]["executive_summary"] == (
        "Revenue per unit was €472.38 in August 2026."
    )
