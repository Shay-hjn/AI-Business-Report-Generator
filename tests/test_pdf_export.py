"""PDF export tests. Run with: python -m pytest tests/test_pdf_export.py -q"""

from copy import deepcopy

import pytest

from frontend.pdf_export import build_report_pdf


REPORT = {
    "monthly_kpis": [
        {"month": "2026-05", "total_revenue": 1000, "order_count": 10,
         "units_sold": 12, "average_order_value": 100, "revenue_per_unit": 83.33,
         "revenue_growth_pct": None},
        {"month": "2026-06", "total_revenue": 1500, "order_count": 8,
         "units_sold": 9, "average_order_value": 187.50, "revenue_per_unit": 166.67,
         "revenue_growth_pct": 50.0},
    ],
    "comparisons": [
        {"changes": {
            "total_revenue": {"percentage_change": 50.0},
            "order_count": {"percentage_change": -20.0},
            "units_sold": {"percentage_change": -25.0},
            "average_order_value": {"percentage_change": 87.5},
            "revenue_per_unit": {"percentage_change": 100.0},
        }}
    ],
    "revenue_breakdowns": {
        "2026-05": {"category": {"Electronics": 900, "Office": 100},
                    "region": {"North": 700, "South": 300}},
        "2026-06": {"category": {"Electronics": 1100, "Office": 400},
                    "region": {"North": 800, "South": 700}},
    },
    "narrative_generated": True,
    "ai_report": {
        "executive_summary": "Revenue rose 50% to €1,500 despite fewer orders.",
        "key_insights": ["Average order value increased.", "Order count decreased."],
        "notable_changes": ["Electronics gained revenue.", "South grew faster."],
    },
}


def test_pdf_contains_valid_header_and_content():
    content = build_report_pdf(REPORT, "example.csv", "18 Oct 2026, 17:30 CEST")
    assert content.startswith(b"%PDF-")
    assert content.rstrip().endswith(b"%%EOF")
    assert len(content) > 5000


def test_pdf_works_without_ai_narrative():
    fallback = deepcopy(REPORT)
    fallback["narrative_generated"] = False
    fallback["ai_report"] = None
    assert build_report_pdf(fallback, "example.csv").startswith(b"%PDF-")


def test_pdf_handles_unchanged_growth_and_single_month():
    single_month = deepcopy(REPORT)
    single_month["monthly_kpis"] = [single_month["monthly_kpis"][0]]
    single_month["monthly_kpis"][0]["revenue_growth_pct"] = None
    single_month["comparisons"] = []
    single_month["revenue_breakdowns"] = {
        "2026-05": single_month["revenue_breakdowns"]["2026-05"]
    }
    assert build_report_pdf(single_month, "one_month.csv").startswith(b"%PDF-")


def test_pdf_rejects_missing_monthly_kpis():
    with pytest.raises(ValueError, match="monthly KPIs"):
        build_report_pdf({}, "empty.csv")


def test_pdf_escapes_source_and_ai_text():
    unusual = deepcopy(REPORT)
    unusual["ai_report"]["executive_summary"] = "Growth <30% & increased; € special chars."
    assert build_report_pdf(unusual, "sales <June> & 2026.csv").startswith(b"%PDF-")


def test_pdf_punctuation_is_renderable_in_selected_font():
    """Prevent square glyphs in names using non-breaking hyphens."""
    from frontend.pdf_export import _font_names, _safe_pdf_text

    regular, _ = _font_names()
    text = "Noise\u2011Cancelling Headset; revenue\u2011volume, 31.36% \u2212 decline"
    assert _safe_pdf_text(text, regular) == (
        "Noise-Cancelling Headset; revenue-volume, 31.36% - decline"
    )


def test_pdf_charts_show_both_period_values_for_each_segment():
    """Never show only the latest value beside two different month bars."""
    from reportlab.graphics.shapes import String

    from frontend.pdf_export import _font_names, _segment_chart

    regular, bold = _font_names()
    months = ["2026-05", "2026-06"]
    chart = _segment_chart(
        ["Electronics", "Office"], REPORT["revenue_breakdowns"],
        months, "category", regular, bold,
    )
    texts = [shape.text for shape in chart.contents if isinstance(shape, String)]
    assert "May 2026" in texts and "Jun 2026" in texts
    # Electronics and Office amounts for BOTH May and June must be visible.
    for expected in ("€900.00", "€1,100.00", "€100.00", "€400.00"):
        assert expected in texts


def test_pdf_charts_show_zeros_for_absent_category_in_each_period():
    from reportlab.graphics.shapes import String

    from frontend.pdf_export import _font_names, _segment_chart

    regular, bold = _font_names()
    changes = {
        "2026-05": {"category": {"Electronics": 49622.00}},
        "2026-06": {"category": {"Accessories": 57920.70}},
    }
    chart = _segment_chart(
        ["Accessories", "Electronics"], changes,
        ["2026-05", "2026-06"], "category", regular, bold,
    )
    texts = [shape.text for shape in chart.contents if isinstance(shape, String)]
    assert texts.count("€0.00") == 2
    assert "€49,622.00" in texts and "€57,920.70" in texts


def test_monthly_chart_labels_exact_euro_values_above_points():
    """Labels must be exact and visibly positioned above their plotted points."""
    from reportlab.graphics.shapes import Circle, String
    from frontend.pdf_export import _font_names, _monthly_chart

    regular, bold = _font_names()
    chart = _monthly_chart(REPORT["monthly_kpis"], regular, bold)
    assert chart.height >= 240  # Avoid the old cramped 112-point chart.
    points = [shape for shape in chart.contents if isinstance(shape, Circle)]
    labels = [shape for shape in chart.contents if isinstance(shape, String)]
    assert len(points) == 2
    for value, point in zip((1000, 1500), points):
        amount = f"€{value:,.2f}"
        matching = [label for label in labels if label.text == amount]
        assert len(matching) == 1
        assert matching[0].y > point.cy
        assert matching[0].x == pytest.approx(point.cx)


def test_monthly_chart_uses_centered_categorical_positions():
    """With two months, dots should be inset like Streamlit's Altair chart."""
    from reportlab.graphics.shapes import Circle
    from frontend.pdf_export import CONTENT_WIDTH, _font_names, _monthly_chart

    regular, bold = _font_names()
    chart = _monthly_chart(REPORT["monthly_kpis"], regular, bold)
    points = [shape for shape in chart.contents if isinstance(shape, Circle)]
    assert points[0].cx > 0.20 * CONTENT_WIDTH
    assert points[1].cx < 0.80 * CONTENT_WIDTH
    assert points[0].cy < points[1].cy


def test_full_report_has_room_for_separate_comparison_charts():
    """The printable report uses three pages instead of a cramped chart page."""
    import re

    content = build_report_pdf(REPORT, "example.csv", "18 Oct 2026, 17:30 CEST")
    # PDF page objects are visible in ReportLab's PDF dictionary output.
    assert len(re.findall(rb"/Type\s*/Page\b", content)) == 3


def test_pdf_monthly_trend_has_dense_y_axis_ticks():
    """Avoid the original three-tick chart that concealed exact positions."""
    from reportlab.graphics.shapes import Line, String
    from frontend.pdf_export import _font_names, _monthly_chart

    regular, bold = _font_names()
    fixture = deepcopy(REPORT)
    fixture["monthly_kpis"][0]["total_revenue"] = 75536.85
    fixture["monthly_kpis"][1]["total_revenue"] = 127328.85
    chart = _monthly_chart(fixture["monthly_kpis"], regular, bold)
    ticks = [item for item in chart.contents if isinstance(item, String)
             and item.text.startswith("€") and not "." in item.text]
    assert chart.height >= 300
    assert 7 <= len(ticks) <= 10, [tick.text for tick in ticks]
    assert sum(isinstance(shape, Line) for shape in chart.contents) >= 7


def test_pdf_three_pages_when_ai_and_segment_charts_present():
    """Use one narrative page, KPI/trend page, and comparisons page."""
    import re
    content = build_report_pdf(REPORT, "example.csv", "18 Oct 2026, 17:30 CEST")
    assert len(re.findall(rb"/Type\s*/Page\b", content)) == 3


def test_streamlit_only_dots_have_hover_tooltip():
    """The text overlay must never generate a hover popup or extra fields."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "frontend" / "app.py").read_text(
        encoding="utf-8"
    )
    module = ast.parse(source)
    trend = next(node for node in module.body
                 if isinstance(node, ast.FunctionDef) and node.name == "revenue_trend_chart")

    def mark_call(name):
        return next(node for node in ast.walk(trend)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == name)

    for name in ("mark_text", "mark_line"):
        call = mark_call(name)
        tooltip = next(item.value for item in call.keywords if item.arg == "tooltip")
        assert isinstance(tooltip, ast.Constant) and tooltip.value is False

    # The point layer is the only one with explicit tooltip encoding.
    tooltip_fields = [
        node for node in ast.walk(trend) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "Tooltip"
    ]
    assert len(tooltip_fields) == 2
    assert [node.args[0].value for node in tooltip_fields] == ["Month:N", "Revenue:Q"]
    assert "RevenueLabel" in source  # The visible exact-euro text remains.



def _record_pdf_paragraphs(monkeypatch):
    """Observe ReportLab headings without relying on a PDF parser package."""
    import frontend.pdf_export as pdf_module

    rendered_text = []
    original = pdf_module.Paragraph

    def record(text, style, *args, **kwargs):
        rendered_text.append(text)
        return original(text, style, *args, **kwargs)

    monkeypatch.setattr(pdf_module, "Paragraph", record)
    return rendered_text


def test_single_month_pdf_header_and_breakdown_section(monkeypatch):
    """A single reporting month should not be shown as a date range."""
    text = _record_pdf_paragraphs(monkeypatch)
    single = deepcopy(REPORT)
    single["monthly_kpis"] = [single["monthly_kpis"][0]]
    single["comparisons"] = []
    single["revenue_breakdowns"] = {
        "2026-05": single["revenue_breakdowns"]["2026-05"]
    }
    build_report_pdf(single, "one_month.csv", "18 Oct 2026")
    assert "May 2026  |  EUR" in text
    assert "May 2026 - May 2026  |  EUR" not in text
    assert "Revenue Breakdown - May 2026" in text
    assert "Segment Revenue Comparisons" not in text


def test_single_month_segment_chart_has_one_bar_and_amount_per_segment():
    """Do not draw two identical bars or duplicate labels for one month."""
    from reportlab.graphics.shapes import Rect, String
    from frontend.pdf_export import _font_names, _single_segment_chart

    regular, bold = _font_names()
    chart = _single_segment_chart(
        ["Electronics", "Office"],
        {"2026-05": REPORT["revenue_breakdowns"]["2026-05"]},
        "2026-05", "category", regular, bold,
    )
    rectangles = [shape for shape in chart.contents if isinstance(shape, Rect)]
    strings = [shape.text for shape in chart.contents if isinstance(shape, String)]
    # Background + one legend swatch + one bar per category.
    assert len(rectangles) == 4
    assert strings.count("May 2026") == 1
    assert strings.count("€900.00") == 1
    assert strings.count("€100.00") == 1
    assert strings.count("Electronics") == 1
    assert strings.count("Office") == 1


def test_two_month_pdf_still_has_comparison_charts_and_range(monkeypatch):
    """Single-month presentation must not change existing comparisons."""
    text = _record_pdf_paragraphs(monkeypatch)
    build_report_pdf(REPORT, "example.csv", "18 Oct 2026")
    assert "May 2026 - Jun 2026  |  EUR" in text
    assert "Segment Revenue Comparisons" in text
    assert "Revenue Breakdown - Jun 2026" not in text


def test_nonconsecutive_pdf_uses_reporting_period_wording(monkeypatch):
    """Missing months must not be mislabeled as month-over-month changes."""
    text = _record_pdf_paragraphs(monkeypatch)
    gapped = deepcopy(REPORT)
    gapped["monthly_kpis"] = [
        {**gapped["monthly_kpis"][0], "month": "2026-03"},
        {**gapped["monthly_kpis"][1], "month": "2026-05"},
    ]
    gapped["revenue_breakdowns"] = {
        "2026-03": gapped["revenue_breakdowns"]["2026-05"],
        "2026-05": gapped["revenue_breakdowns"]["2026-06"],
    }
    build_report_pdf(gapped, "missing_month.csv", "18 Oct 2026")
    assert any("Revenue Growth vs Prior Period" in item for item in text)
    assert any("+50.00% vs prior reporting period" in item for item in text)
    assert any("Mar 2026 to May 2026 (1 missing month)" in item for item in text)


def test_monthly_chart_value_labels_use_contrasting_color_and_mask():
    """Exact-euro labels should remain readable even when the line crosses them."""
    from reportlab.graphics.shapes import Rect, String
    from frontend.pdf_export import LABEL_INK, _font_names, _monthly_chart

    regular, bold = _font_names()
    chart = _monthly_chart(REPORT["monthly_kpis"], regular, bold)
    label_strings = [
        shape for shape in chart.contents
        if isinstance(shape, String) and shape.text in {"€1,000.00", "€1,500.00"}
    ]
    assert label_strings
    assert all(shape.fillColor == LABEL_INK for shape in label_strings)
    # Background chart panel + at least one mask rectangle behind each value label.
    masks = [shape for shape in chart.contents if isinstance(shape, Rect)]
    assert len(masks) >= 1 + len(label_strings)


def test_segment_chart_uses_blue_red_comparison_palette():
    """Comparison charts should avoid the earlier gray/green improvement palette."""
    from reportlab.graphics.shapes import Rect
    from frontend.pdf_export import COMPARE_NEW, COMPARE_OLD, _font_names, _segment_chart

    regular, bold = _font_names()
    chart = _segment_chart(
        ["Electronics", "Office"], REPORT["revenue_breakdowns"],
        ["2026-05", "2026-06"], "category", regular, bold,
    )
    fills = [shape.fillColor for shape in chart.contents if isinstance(shape, Rect)]
    assert COMPARE_OLD in fills
    assert COMPARE_NEW in fills
