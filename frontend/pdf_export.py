"""Create a printable management report from the existing FastAPI response.

All figures and narrative are reused as-is from the response: this module never
reads the CSV, recalculates analytics, connects to a database, or calls an LLM.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from math import ceil, floor, log10
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String


NAVY = colors.HexColor("#12283C")
INK = colors.HexColor("#1A3044")
MUTED = colors.HexColor("#667C8E")
TEAL = colors.HexColor("#087F77")
TEAL_LIGHT = colors.HexColor("#DDF3EF")
PALE = colors.HexColor("#F3F7F9")
GRID = colors.HexColor("#DDE8ED")
COMPARE_OLD = colors.HexColor("#4F83CC")
COMPARE_NEW = colors.HexColor("#D65A5A")
LABEL_INK = NAVY
WHITE = colors.white
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 43
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


def _font_names():
    """Use a local Unicode font if installed; never bundle fonts with the app."""
    choices = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf")),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ),
    ]
    for regular_path, bold_path in choices:
        if regular_path.is_file() and bold_path.is_file():
            regular, bold = "SI-Regular", "SI-Bold"
            if regular not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(regular, str(regular_path)))
            if bold not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(bold, str(bold_path)))
            pdfmetrics.registerFontFamily(regular, normal=regular, bold=bold)
            return regular, bold
    return "Helvetica", "Helvetica-Bold"



# The LLM may use typography such as non-breaking hyphens (U+2011).
# Some Windows PDF fonts do not contain those glyphs, which creates black
# squares in the exported document. Normalize presentation-only punctuation
# without modifying the stored AI narrative or any numerical values.
_PDF_PUNCTUATION = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-", "\u00ad": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00a0": " ", "\u202f": " ", "\u200b": "", "\ufeff": "",
})


def _safe_pdf_text(text, font_name):
    """Normalize unsupported punctuation and avoid invisible PDF glyphs.

    Prefer the original Unicode characters when the chosen embedded font
    supports them; use '?' only for otherwise unsupported code points.
    """
    normalized = str(text).translate(_PDF_PUNCTUATION)
    face = pdfmetrics.getFont(font_name).face
    available = getattr(face, "charWidths", None)
    if available is None:
        return normalized
    return "".join(
        character if character in "\n\r\t" or ord(character) in available else "?"
        for character in normalized
    )


def _money(value):
    amount = float(value)
    return f"{'-' if amount < 0 else ''}€{abs(amount):,.2f}"


def _month(value):
    try:
        return datetime.strptime(str(value), "%Y-%m").strftime("%b %Y")
    except ValueError:
        return str(value)


def _short_money(value):
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"€{value / 1_000_000:,.1f}m"
    if abs_value >= 1000:
        return f"€{value / 1000:,.0f}k"
    return f"€{value:,.0f}"


def _month_distance(start, end):
    try:
        start_dt = datetime.strptime(str(start), "%Y-%m")
        end_dt = datetime.strptime(str(end), "%Y-%m")
    except ValueError:
        return None
    return (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)


def _comparison_context(previous_month, latest_month):
    if not previous_month or not latest_month:
        return {
            "has_prior": False,
            "is_consecutive": False,
            "missing_months": 0,
            "delta_suffix": "No prior comparison",
            "growth_label": "Revenue Growth",
            "growth_note": "Second month required",
        }

    gap = _month_distance(previous_month, latest_month)
    missing_months = max((gap or 0) - 1, 0)
    previous_label = _month(previous_month)
    latest_label = _month(latest_month)

    if gap == 1:
        return {
            "has_prior": True,
            "is_consecutive": True,
            "missing_months": 0,
            "delta_suffix": "vs previous month",
            "growth_label": "MoM Revenue Growth",
            "growth_note": f"{previous_label} to {latest_label}",
        }

    gap_note = (
        f" ({missing_months} missing month{'s' if missing_months != 1 else ''})"
        if missing_months > 0 else ""
    )
    return {
        "has_prior": True,
        "is_consecutive": False,
        "missing_months": missing_months,
        "delta_suffix": "vs prior reporting period",
        "growth_label": "Revenue Growth vs Prior Period",
        "growth_note": f"{previous_label} to {latest_label}{gap_note}",
    }


def _delta(comparisons, metric):
    if not comparisons:
        return None
    return comparisons[-1].get("changes", {}).get(metric, {}).get("percentage_change")


def _delta_text(delta, comparison_suffix="vs previous month"):
    if delta is None:
        return "No prior comparison"
    if delta > 0:
        return f"+{delta:.2f}% {comparison_suffix}"
    if delta < 0:
        return f"{delta:.2f}% {comparison_suffix}"
    return "0.00% - unchanged"


def _paragraph(text, style):
    # Escape AFTER glyph normalization so AI prose cannot inject PDF markup.
    safe = escape(_safe_pdf_text(text, style.fontName)).replace("\n", "<br/>")
    return Paragraph(safe, style)


def _styles(regular, bold):
    return {
        "eyebrow": ParagraphStyle(
            "SIEyebrow", fontName=bold, fontSize=8, leading=13, textColor=TEAL,
            spaceAfter=5, tracking=1.0,
        ),
        "title": ParagraphStyle(
            "SITitle", fontName=bold, fontSize=23, leading=30, textColor=NAVY,
            spaceAfter=5,
        ),
        "sub": ParagraphStyle(
            "SISubtitle", fontName=regular, fontSize=10, leading=15,
            textColor=MUTED, spaceAfter=12,
        ),
        "meta_head": ParagraphStyle(
            "SIMetaHead", fontName=bold, fontSize=7.1, leading=10,
            textColor=MUTED,
        ),
        "meta_value": ParagraphStyle(
            "SIMetaValue", fontName=regular, fontSize=8.8, leading=12,
            textColor=INK,
        ),
        "section": ParagraphStyle(
            "SISection", fontName=bold, fontSize=12.6, leading=18,
            textColor=NAVY, spaceBefore=12, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "SIBody", fontName=regular, fontSize=9, leading=15,
            textColor=INK, spaceAfter=0,
        ),
        "bullet": ParagraphStyle(
            "SIBullet", fontName=regular, fontSize=8.9, leading=14.5,
            textColor=INK, leftIndent=14, firstLineIndent=0,
            bulletIndent=3, bulletFontName=bold, bulletFontSize=9,
            spaceAfter=7,
        ),
        "kpi_label": ParagraphStyle(
            "SIKpiLabel", fontName=bold, fontSize=8, leading=12,
            textColor=MUTED,
        ),
        "kpi_value": ParagraphStyle(
            "SIKpiValue", fontName=bold, fontSize=14.7, leading=20,
            textColor=NAVY,
        ),
        "kpi_delta": ParagraphStyle(
            "SIKpiDelta", fontName=regular, fontSize=7.3, leading=11,
            textColor=MUTED,
        ),
        "chart_title": ParagraphStyle(
            "SIChartTitle", fontName=bold, fontSize=10, leading=15,
            textColor=INK, spaceBefore=9, spaceAfter=5,
        ),
        "notice": ParagraphStyle(
            "SINotice", fontName=regular, fontSize=9, leading=15,
            textColor=MUTED, spaceAfter=10,
        ),
    }


def _page_details(canvas, doc, regular, bold):
    canvas.saveState()
    canvas.setFillColor(TEAL)
    canvas.roundRect(MARGIN, PAGE_HEIGHT - 37, 6, 6, 2, stroke=0, fill=1)
    canvas.setFillColor(NAVY)
    canvas.setFont(bold, 9)
    canvas.drawString(MARGIN + 12, PAGE_HEIGHT - 37, "SALES INTELLIGENCE")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.8)
    canvas.line(MARGIN, PAGE_HEIGHT - 47, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 47)
    canvas.line(MARGIN, 44, PAGE_WIDTH - MARGIN, 44)
    canvas.setFont(regular, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 31, "Business Report Generator")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 31, f"Page {doc.page}")
    canvas.restoreState()


def _section(title, styles):
    return Paragraph(escape(title), styles["section"])


def _narrative_list(items, styles):
    if not items:
        return [_paragraph("No findings available for this section.", styles["notice"])]
    return [
        Paragraph(
            escape(_safe_pdf_text(item, styles["bullet"].fontName)).replace("\n", "<br/>"),
            styles["bullet"], bulletText="•",
        )
        for item in items
    ]


def _kpi_table(latest, comparisons, month_before, month_latest, styles, comparison_context):
    growth = latest.get("revenue_growth_pct")
    growth_text = (
        f"{growth:+.2f}%" if growth is not None and growth != 0 else
        ("0.00%" if growth is not None else "N/A")
    )
    period_note = comparison_context["growth_note"]
    cards = [
        ("Total Revenue", _money(latest["total_revenue"]),
         _delta_text(_delta(comparisons, "total_revenue"), comparison_context["delta_suffix"])),
        ("Order Count", f"{int(latest['order_count']):,}",
         _delta_text(_delta(comparisons, "order_count"), comparison_context["delta_suffix"])),
        ("Units Sold", f"{int(latest['units_sold']):,}",
         _delta_text(_delta(comparisons, "units_sold"), comparison_context["delta_suffix"])),
        ("Average Order Value", _money(latest["average_order_value"]),
         _delta_text(_delta(comparisons, "average_order_value"), comparison_context["delta_suffix"])),
        ("Revenue per Unit", _money(latest["revenue_per_unit"]),
         _delta_text(_delta(comparisons, "revenue_per_unit"), comparison_context["delta_suffix"])),
        (comparison_context["growth_label"], growth_text, period_note),
    ]
    col_width = CONTENT_WIDTH / 3
    cells = []
    for label, value, delta_text in cards:
        cells.append([
            _paragraph(label, styles["kpi_label"]),
            _paragraph(value, styles["kpi_value"]),
            _paragraph(delta_text, styles["kpi_delta"]),
        ])
    # Each cell contains three short paragraphs. Insets act as white gutters.
    rows = [[cells[0], cells[1], cells[2]], [cells[3], cells[4], cells[5]]]
    table = Table(rows, colWidths=[col_width] * 3, rowHeights=[60, 60])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 13),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("INNERGRID", (0, 0), (-1, -1), 7, WHITE),
        ("BOX", (0, 0), (-1, -1), 0.7, GRID),
    ]))
    return table


def _monthly_tick_step(axis_max):
    """Choose a readable Y-axis interval for roughly 7-9 horizontal ticks.

    Use human-friendly intervals (1/2/2.5/5 times powers of ten) rather than
    drawing just the minimum, midpoint and maximum as the old PDF did.
    """
    target = max(axis_max / 7.5, 0.0001)
    magnitude = 10 ** floor(log10(target))
    candidates = [factor * magnitude for factor in (1, 2, 2.5, 5, 10)]
    return min(candidates, key=lambda step: abs(axis_max / step - 7.5))


def _monthly_chart(monthly, regular, bold):
    """Printable equivalent of the Streamlit trend: tall chart, many gridlines.

    Keep the plot's horizontal categorical positioning centered, the vertical
    scale zero-based, and label each point with its *exact* euro total.
    """
    width, height = CONTENT_WIDTH, 332
    chart = Drawing(width, height)
    chart.add(Rect(0, 0, width, height, fillColor=PALE,
                   strokeColor=GRID, strokeWidth=0.6))

    # Dedicate almost the entire width/height to the plot, as in Streamlit.
    left, right, bottom, top = 72, width - 30, 36, height - 29
    values = [float(item["total_revenue"]) for item in monthly]
    axis_max = max(max(values, default=0.0) * 1.17, 1.0)
    tick_step = _monthly_tick_step(axis_max)
    ticks = int(axis_max / tick_step) + 1

    chart.add(String(12, height - 14, "Revenue (€)", fontName=bold,
                     fontSize=8, fillColor=MUTED))
    for index in range(ticks):
        amount = index * tick_step
        y = bottom + (top - bottom) * amount / axis_max
        chart.add(Line(left, y, right, y, strokeColor=GRID, strokeWidth=0.7))
        chart.add(String(left - 9, y - 3, _short_money(amount),
                         fontName=regular, fontSize=8, fillColor=MUTED,
                         textAnchor="end"))
    if not values:
        return chart

    # Categorical month centers match the Altair chart in the app.
    plot_width = right - left
    positions = [left + plot_width * (index + 0.5) / len(values)
                 for index in range(len(values))]
    points = []
    for x, value in zip(positions, values):
        points.extend([x, bottom + (top - bottom) * max(value, 0) / axis_max])
    if len(values) > 1:
        chart.add(PolyLine(points, strokeColor=TEAL, strokeWidth=2.8))

    label_size = 9.3 if len(values) <= 4 else 7.0
    placed_labels = []
    for index, (x, value) in enumerate(zip(positions, values)):
        y = bottom + (top - bottom) * max(value, 0) / axis_max
        chart.add(Circle(x, y, 4.1, fillColor=TEAL,
                         strokeColor=WHITE, strokeWidth=1.2))
        amount = _money(value)
        label_width = pdfmetrics.stringWidth(amount, bold, label_size)
        label_y = y + 14
        # For long histories, adjacent values may be almost identical.
        # Stagger only labels that would visibly overlap, retaining each
        # amount exactly and keeping it ABOVE its own data point.
        while any(
            abs(x - placed_x) < (label_width + placed_width) / 2 + 3
            and abs(label_y - placed_y) < label_size + 3
            for placed_x, placed_y, placed_width in placed_labels
        ) and label_y + 12 < height - 14:
            label_y += label_size + 4
        placed_labels.append((x, label_y, label_width))
        background_pad = 3
        chart.add(Rect(
            x - label_width / 2 - background_pad,
            label_y - 2,
            label_width + background_pad * 2,
            label_size + 4,
            fillColor=PALE,
            strokeColor=None,
        ))
        chart.add(String(x, label_y, amount, fontName=bold,
                         fontSize=label_size, fillColor=LABEL_INK,
                         textAnchor="middle"))
        if len(values) <= 8 or index % ceil(len(values) / 8) == 0 or index == len(values) - 1:
            chart.add(String(x, 13, str(monthly[index]["month"]),
                             fontName=regular, fontSize=8.6,
                             fillColor=MUTED, textAnchor="middle"))
    return chart


def _fit_label(text, font_name, max_width):
    # Keep every segment present; only trim unusually long displayed labels.
    label = _safe_pdf_text(text, font_name)
    if pdfmetrics.stringWidth(label, font_name, 8.2) <= max_width:
        return label
    while label and pdfmetrics.stringWidth(label + "...", font_name, 8.2) > max_width:
        label = label[:-1]
    return label + "..."


def _segment_chart(names, breakdowns, month_keys, dimension, regular, bold):
    """Draw comparable bars with an explicit amount for EACH month.

    The earlier version labeled only the newest month. That made historical
    bars appear to be incorrectly valued (e.g. Electronics had an August bar
    but a single label reading '€0' for September).
    """
    row_height = 30
    width, height = CONTENT_WIDTH, 48 + row_height * len(names)
    chart = Drawing(width, height)
    chart.add(Rect(0, 0, width, height, fillColor=PALE, strokeColor=GRID, strokeWidth=0.6))

    earlier, latest = month_keys[0], month_keys[-1]
    old_amounts = breakdowns.get(earlier, {}).get(dimension, {})
    new_amounts = breakdowns.get(latest, {}).get(dimension, {})

    # Each bar and each value use the same color as their month in the legend.
    chart.add(Rect(13, height - 20, 9, 9, fillColor=COMPARE_OLD, strokeColor=None))
    chart.add(String(27, height - 19, _month(earlier), fontName=regular,
                     fontSize=8, fillColor=MUTED))
    chart.add(Rect(131, height - 20, 9, 9, fillColor=COMPARE_NEW, strokeColor=None))
    chart.add(String(145, height - 19, _month(latest), fontName=regular,
                     fontSize=8, fillColor=MUTED))

    # Reserve a fixed value column. Both months get exact euro values, rather
    # than approximate and potentially misleading rounded '€k' labels.
    x0 = 154
    plot_width = width - x0 - 91
    amount_right = width - 11
    maximum = max(
        (float(amount) for name in names for amount in (
            old_amounts.get(name, 0), new_amounts.get(name, 0))),
        default=0.0,
    )
    maximum = max(maximum, 1.0)
    for factor in (0, 0.5, 1):
        x = x0 + factor * plot_width
        chart.add(Line(x, 17, x, height - 24,
                       strokeColor=GRID, strokeWidth=0.7))

    for index, name in enumerate(names):
        row_bottom = height - 59 - index * row_height
        # One labelled row has a blue earlier-period bar above a red latest-period bar.
        chart.add(String(12, row_bottom + 13,
                         _fit_label(name, regular, x0 - 24),
                         fontName=regular, fontSize=8.2, fillColor=INK))
        old_value = float(old_amounts.get(name, 0))
        new_value = float(new_amounts.get(name, 0))
        chart.add(Rect(x0, row_bottom + 19,
                       plot_width * max(old_value, 0) / maximum, 8,
                       fillColor=COMPARE_OLD, strokeColor=None))
        chart.add(Rect(x0, row_bottom + 5,
                       plot_width * max(new_value, 0) / maximum, 8,
                       fillColor=COMPARE_NEW, strokeColor=None))
        chart.add(String(amount_right, row_bottom + 20, _money(old_value),
                         fontName=regular, fontSize=7.4, fillColor=COMPARE_OLD,
                         textAnchor="end"))
        chart.add(String(amount_right, row_bottom + 6, _money(new_value),
                         fontName=bold, fontSize=7.4, fillColor=COMPARE_NEW,
                         textAnchor="end"))
        if index < len(names) - 1:
            chart.add(Line(12, row_bottom - 3, width - 12, row_bottom - 3,
                           strokeColor=GRID, strokeWidth=0.45))

    return chart


def _single_segment_chart(names, breakdowns, month, dimension, regular, bold):
    """Single-month revenue breakdown: one bar and one exact value per group.

    A snapshot has no comparison period, so drawing a second identical bar
    would incorrectly imply a month-over-month comparison.
    """
    row_height = 30
    width, height = CONTENT_WIDTH, 44 + row_height * len(names)
    chart = Drawing(width, height)
    chart.add(Rect(0, 0, width, height, fillColor=PALE,
                   strokeColor=GRID, strokeWidth=0.6))

    amounts = breakdowns.get(month, {}).get(dimension, {})
    chart.add(Rect(13, height - 21, 9, 9, fillColor=COMPARE_NEW, strokeColor=None))
    chart.add(String(27, height - 20, _month(month), fontName=regular,
                     fontSize=8, fillColor=MUTED))

    x0 = 154
    plot_width = width - x0 - 91
    amount_right = width - 11
    maximum = max((float(amounts.get(name, 0)) for name in names), default=0.0)
    maximum = max(maximum, 1.0)
    for factor in (0, 0.5, 1):
        x = x0 + factor * plot_width
        chart.add(Line(x, 13, x, height - 26,
                       strokeColor=GRID, strokeWidth=0.7))

    for index, name in enumerate(names):
        y = height - 50 - index * row_height
        value = float(amounts.get(name, 0))
        chart.add(String(12, y + 3, _fit_label(name, regular, x0 - 24),
                         fontName=regular, fontSize=8.2, fillColor=INK))
        chart.add(Rect(x0, y, plot_width * max(value, 0) / maximum, 10,
                       fillColor=COMPARE_NEW, strokeColor=None))
        chart.add(String(amount_right, y + 3, _money(value), fontName=bold,
                         fontSize=7.4, fillColor=COMPARE_NEW, textAnchor="end"))
        if index < len(names) - 1:
            chart.add(Line(12, y - 10, width - 12, y - 10,
                           strokeColor=GRID, strokeWidth=0.45))
    return chart


def _segments(breakdowns, dimension, regular, bold, styles):
    months = sorted(breakdowns)[-2:]
    if not months:
        return []
    latest = breakdowns[months[-1]].get(dimension, {})
    names = sorted(
        {name for month in months for name in breakdowns[month].get(dimension, {})},
        key=lambda name: (-latest.get(name, 0), name),
    )
    if not names:
        return []
    title = "Revenue by Category" if dimension == "category" else "Revenue by Region"
    chunks = [names[i:i + 11] for i in range(0, len(names), 11)]
    elements = []
    for i, subset in enumerate(chunks, 1):
        name = title if len(chunks) == 1 else f"{title} ({i}/{len(chunks)})"
        chart = (
            _single_segment_chart(subset, breakdowns, months[0], dimension,
                                  regular, bold)
            if len(months) == 1
            else _segment_chart(subset, breakdowns, months, dimension,
                                regular, bold)
        )
        elements.append(KeepTogether([
            Paragraph(name, styles["chart_title"]),
            chart,
        ]))
    return elements


def build_report_pdf(report: dict, source_filename: str, generated_at: str = "") -> bytes:
    """Return a complete PDF as bytes, using only the already-generated report.

    This function is deterministic for the same report, filename and timestamp.
    It does not access the backend, source CSV, internet, or a database.
    """
    monthly = report.get("monthly_kpis") or []
    if not monthly:
        raise ValueError("Cannot export a report without monthly KPIs.")

    regular, bold = _font_names()
    styles = _styles(regular, bold)
    comparisons = report.get("comparisons") or []
    breakdowns = report.get("revenue_breakdowns") or {}
    latest = monthly[-1]
    initial_month = _month(monthly[0]["month"])
    final_month = _month(latest["month"])
    previous_month = monthly[-2]["month"] if len(monthly) >= 2 else None
    comparison_context = _comparison_context(previous_month, latest["month"])
    period_label = (initial_month if len(monthly) == 1
                    else f"{initial_month} - {final_month}")
    when = generated_at or datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=MARGIN, leftMargin=MARGIN,
        topMargin=62, bottomMargin=57,
        title="Business Performance Report", author="Sales Intelligence",
        pageCompression=1,
    )

    story = [
        Paragraph("MANAGEMENT REPORT", styles["eyebrow"]),
        Paragraph("Business Performance Report", styles["title"]),
        Paragraph(f"{escape(period_label)}  |  EUR", styles["sub"]),
    ]
    meta = Table([
        [Paragraph("SOURCE FILE", styles["meta_head"]),
         Paragraph("GENERATED", styles["meta_head"])],
        [_paragraph(source_filename, styles["meta_value"]),
         _paragraph(when, styles["meta_value"])],
    ], colWidths=[CONTENT_WIDTH * 0.60, CONTENT_WIDTH * 0.40])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, GRID),
    ]))
    story.extend([meta, Spacer(1, 11)])

    ai = report.get("ai_report")
    has_ai = bool(report.get("narrative_generated") and ai)
    story.append(_section("AI Management Report", styles))
    if has_ai:
        summary_content = [
            Paragraph("EXECUTIVE SUMMARY", styles["eyebrow"]),
            _paragraph(ai.get("executive_summary", ""), styles["body"]),
        ]
        summary = Table([[summary_content]], colWidths=[CONTENT_WIDTH])
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
            ("LINEBEFORE", (0, 0), (0, -1), 3.5, TEAL),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 17),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ]))
        story.extend([summary, Spacer(1, 3)])
        story.append(_section("Key Insights", styles))
        story.extend(_narrative_list(ai.get("key_insights", []), styles))
        story.append(_section("Notable Changes", styles))
        story.extend(_narrative_list(ai.get("notable_changes", []), styles))
        # The charts/KPIs start on a fresh page in a printable report.
        # Longer narratives already flow naturally onto a continuation page.
        # In that case, let the KPI section use the remaining space rather
        # than inserting an extra break that leaves a mostly empty page.
        narrative_length = len(ai.get("executive_summary", "")) + sum(
            len(item) for item in ai.get("key_insights", []) + ai.get("notable_changes", [])
        )
        if narrative_length < 1500:
            story.append(PageBreak())
    else:
        story.append(_paragraph(
            "The AI narrative was unavailable for this run. "
            "The calculated KPIs and visualizations are included below.", styles["notice"],
        ))

    story.append(KeepTogether([
        _section("Performance Snapshot", styles),
        _kpi_table(
            latest,
            comparisons,
            _month(previous_month) if previous_month else None,
            final_month,
            styles,
            comparison_context,
        ),
    ]))
    story.append(Spacer(1, 5))
    story.append(KeepTogether([
        _section("Revenue Analytics", styles),
        Paragraph("Monthly Revenue Trend", styles["chart_title"]),
        _monthly_chart(monthly, regular, bold),
    ]))
    if breakdowns:
        # Avoid squeezing three charts onto one page. Keep both comparison
        # charts together on the next page whenever their size allows.
        comparison_sections = (
            _segments(breakdowns, "category", regular, bold, styles)
            + _segments(breakdowns, "region", regular, bold, styles)
        )
        if comparison_sections:
            story.append(PageBreak())
            heading = (f"Revenue Breakdown - {final_month}"
                       if len(monthly) == 1 else "Segment Revenue Comparisons")
            story.append(_section(heading, styles))
            story.extend(comparison_sections)

    def render_page(canvas, document):
        _page_details(canvas, document, regular, bold)

    doc.build(story, onFirstPage=render_page, onLaterPages=render_page)
    return buffer.getvalue()
