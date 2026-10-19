"""Focused offline regressions for report wording, product ranks and PDF flow."""

import json
import re
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from reportlab.graphics.shapes import Circle, String
from reportlab.pdfbase import pdfmetrics

from backend.app.analytics.pipeline import analyze_sales_data
from backend.app.services.llm_service import (
    SYSTEM_PROMPT,
    generate_business_report,
    normalize_text_spacing,
)
from frontend.pdf_export import _font_names, _monthly_chart, build_report_pdf


REPORT = {
    "monthly_kpis": [
        {"month": "2026-05", "total_revenue": 1000, "order_count": 10,
         "units_sold": 12, "average_order_value": 100,
         "revenue_per_unit": 83.33, "revenue_growth_pct": None},
        {"month": "2026-06", "total_revenue": 1500, "order_count": 8,
         "units_sold": 9, "average_order_value": 187.50,
         "revenue_per_unit": 166.67, "revenue_growth_pct": 50},
    ],
    "comparisons": [{"changes": {
        "total_revenue": {"percentage_change": 50},
        "order_count": {"percentage_change": -20},
        "units_sold": {"percentage_change": -25},
        "average_order_value": {"percentage_change": 87.5},
        "revenue_per_unit": {"percentage_change": 100},
    }}],
    "revenue_breakdowns": {
        "2026-05": {"category": {"Office": 1000}, "region": {"North": 1000}},
        "2026-06": {"category": {"Office": 1500}, "region": {"North": 1500}},
    },
    "narrative_generated": True,
    "ai_report": {"executive_summary": "Revenue rose 50%.",
                  "key_insights": [], "notable_changes": []},
}


def _analysis():
    rows = []
    for name, revenue in [
        ("Business Tablet", 14097.85),
        ("Meeting Room Table", 16845.95),
        ("Standing Desk Pro", 23331.05),
        ("Mini PC Workstation", 21333.30),
    ]:
        rows.append({
            "order_id": name, "date": "2026-08-01", "customer_id": name,
            "product": name, "category": "Office", "region": "North",
            "quantity": 1, "unit_price": revenue,
            "discount_pct": 0, "total_sales": revenue,
        })
    return analyze_sales_data(pd.DataFrame(rows))


def test_model_receives_explicit_latest_product_ranking():
    answer = {
        "executive_summary": "The sales snapshot covers August 2026.",
        "key_insights": ["Product revenues were not equal."],
        "notable_changes": [],
    }
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(answer))
    result = generate_business_report(_analysis(), client=client)
    assert result["narrative_generated"] is True
    sent = client.models.generate_content.call_args.kwargs["contents"]
    payload = json.loads(sent.split("\n", 1)[1])
    ranking = payload["latest_product_revenue_ranking"]
    assert ranking == {
        "month": "2026-08",
        "products": [
            {"rank": 1, "name": "Standing Desk Pro", "revenue": 23331.05},
            {"rank": 2, "name": "Mini PC Workstation", "revenue": 21333.30},
            {"rank": 3, "name": "Meeting Room Table", "revenue": 16845.95},
        ],
    }
    assert client.models.generate_content.call_count == 1


def test_prompt_excludes_unsupported_business_claims_and_repeated_sections():
    assert "stable customer" in SYSTEM_PROMPT
    assert "entered the portfolio" in SYSTEM_PROMPT
    assert "Do not repeat the same event" in SYSTEM_PROMPT
    assert "latest_product_revenue_ranking" in SYSTEM_PROMPT
    assert "(-65.88% increase)" in SYSTEM_PROMPT


def test_display_normalizes_only_redundant_negative_in_positive_direction():
    before = "West rose by €18.00 (-20% increase); latest change (-32.5%)."
    after = normalize_text_spacing(before)
    assert "(20% increase)" in after
    assert "(-32.5%)" in after
    assert "(-20% increase)" not in after


def test_long_monthly_chart_euro_labels_do_not_overlap():
    regular, bold = _font_names()
    values = [105472.50, 114776.60, 130195.10, 134387.30, 150424.70,
              152657.85, 79509.90, 89991.50, 98129.85, 157266.30, 112103.05]
    monthly = [
        {"month": f"2026-{index:02d}", "total_revenue": value}
        for index, value in enumerate(values, 1)
    ]
    chart = _monthly_chart(monthly, regular, bold)
    labels = [item for item in chart.contents
              if isinstance(item, String) and item.text.startswith("€") and "." in item.text]
    points = [item for item in chart.contents if isinstance(item, Circle)]
    assert len(labels) == len(points) == 11
    for label, point, value in zip(labels, points, values):
        assert label.text == f"€{value:,.2f}"
        assert label.y > point.cy
        assert label.x == pytest.approx(point.cx)
    for index, first in enumerate(labels):
        for second in labels[index + 1:]:
            first_width = pdfmetrics.stringWidth(first.text, bold, first.fontSize)
            second_width = pdfmetrics.stringWidth(second.text, bold, second.fontSize)
            overlap_x = abs(first.x-second.x) < (first_width + second_width) / 2
            overlap_y = abs(first.y-second.y) < max(first.fontSize, second.fontSize) + 1
            assert not (overlap_x and overlap_y), (first.text, second.text)


def test_long_narrative_uses_continuation_page_for_kpis_instead_of_blank_page():
    report = deepcopy(REPORT)
    report["ai_report"]["executive_summary"] = (
        "Revenue changed over multiple months, with different movements "
        "in regions and categories. " * 3
    )
    report["ai_report"]["key_insights"] = [
        f"Finding {index}: category and region contributions varied between "
        "reporting months, highlighting different revenue movements. "
        "Verified monthly measures are described here."
        for index in range(7)
    ]
    report["ai_report"]["notable_changes"] = [
        f"Historical change {index}: selected products contributed different "
        "revenue amounts over time and illustrate the reported patterns. "
        "These values are for the supplied period."
        for index in range(7)
    ]
    content = build_report_pdf(report, "long_history.csv", "19 Oct 2026, 03:00")
    assert len(re.findall(rb"/Type\s*/Page\b", content)) == 3


def test_quota_saving_mode_disables_second_content_generation(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_CONTENT_VALIDATION", "0")
    invalid_answer = {
        "executive_summary": "Revenue rose due to stronger customer demand.",
        "key_insights": [], "notable_changes": [],
    }
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(invalid_answer))
    result = generate_business_report(_analysis(), client=client)
    assert result == {"narrative_generated": False, "ai_report": None}
    assert client.models.generate_content.call_count == 1
