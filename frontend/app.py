"""Streamlit interface for the AI Business Report Generator."""

import hashlib
import time
from datetime import datetime
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

from pdf_export import build_report_pdf


API_URL = "http://127.0.0.1:8000/reports"

# Keep the template headers aligned with the backend's CSV validator.
CSV_COLUMNS = [
    "order_id",
    "date",
    "customer_id",
    "product",
    "category",
    "region",
    "quantity",
    "unit_price",
    "discount_pct",
    "total_sales",
]

st.set_page_config(
    page_title="Sales Intelligence | AI Reports",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Native dark theme is configured in .streamlit/config.toml.
# CSS is used only for the custom dashboard layout and widgets.
STYLESHEET = Path(__file__).with_name("styles.css")
st.markdown(
    "<style>\n" + STYLESHEET.read_text(encoding="utf-8") + "\n</style>",
    unsafe_allow_html=True,
    anchors=False,
)


def money(value):
    """Format a revenue metric using the prototype's EUR assumption."""
    number = float(value)
    sign = "-" if number < 0 else ""
    return f"{sign}€{abs(number):,.2f}"


def month_label(value):
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%b %Y")
    except (TypeError, ValueError):
        return str(value)


def section_heading(title, subtitle=""):
    # Omit the subtitle element entirely when no subtitle is requested.
    content = '<div class="si-section-heading">' + f"<h3>{escape(title)}</h3>"
    if subtitle:
        content += f"<p>{escape(subtitle)}</p>"
    content += "</div>"
    st.markdown(content, unsafe_allow_html=True, anchors=False)


def report_list_card(title, items, css_class):
    """Escape AI-generated text before inserting it into custom HTML."""
    if items:
        entries = "".join(f"<li>{escape(str(item))}</li>" for item in items)
    else:
        entries = "<li>No findings available for this section.</li>"
    st.markdown(
        f'<div class="si-report-card {css_class}">'
        f'<h4>{escape(title)}</h4><ul class="si-list">{entries}</ul></div>',
        unsafe_allow_html=True,
        anchors=False,
    )


def percent_delta(comparisons, metric):
    if not comparisons:
        return None
    item = comparisons[-1].get("changes", {}).get(metric, {})
    return item.get("percentage_change")


def kpi_card(label, value, delta, icon, note=None):
    if note is not None:
        text, cls = note, "si-neutral"
    elif delta is None:
        text, cls = "No prior comparison", "si-neutral"
    elif delta > 0:
        text, cls = f"↑ {delta:+.2f}% vs previous month", "si-positive"
    elif delta < 0:
        text, cls = f"↓ {delta:+.2f}% vs previous month", "si-negative"
    else:
        text, cls = "0.00% · unchanged", "si-neutral"
    return (
        '<div class="si-kpi">'
        '<div class="si-kpi-top">'
        f'<span class="si-kpi-label">{escape(label)}</span>'
        f'<span class="si-kpi-icon">{escape(icon)}</span></div>'
        f'<div class="si-kpi-value">{escape(value)}</div>'
        f'<div class="si-kpi-delta {cls}">{escape(text)}</div>'
        "</div>"
    )


def style_chart(chart):
    """Make all Altair charts match the dark dashboard."""
    return (
        chart.properties(background="#111E31")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor="#B7C7DA",
            titleColor="#B7C7DA",
            gridColor="#28384E",
            domainColor="#41536B",
            tickColor="#41536B",
            labelFontSize=12,
            titleFontSize=12,
        )
        .configure_legend(
            labelColor="#D9E7F5",
            titleColor="#D9E7F5",
            labelFontSize=12,
            orient="top",
        )
    )


def revenue_trend_chart(monthly_kpis):
    """Show exact revenue above each dot; only the dots have hover details."""
    df = pd.DataFrame(
        [
            {
                "Month": item["month"],
                "Revenue": float(item["total_revenue"]),
                "RevenueLabel": money(item["total_revenue"]),
            }
            for item in monthly_kpis
        ]
    )
    # Match the printable PDF's zero-based plot and space for value labels.
    axis_max = max(float(df["Revenue"].max()) * 1.17, 1.0)
    month_axis = alt.X(
        "Month:N",
        title=None,
        sort=list(df["Month"]),
        axis=alt.Axis(labelAngle=0, grid=False),
    )
    revenue_axis = alt.Y(
        "Revenue:Q",
        title="Revenue (€)",
        scale=alt.Scale(domain=[0, axis_max]),
        axis=alt.Axis(format="~s", tickCount=8),
    )
    base = alt.Chart(df).encode(x=month_axis, y=revenue_axis)

    # The line and the visible labels have NO tooltip. Only the teal dots
    # respond to hover, showing month and exact revenue (no RevenueLabel).
    line = base.mark_line(color="#37DCC9", strokeWidth=3, tooltip=False)
    dots = base.mark_circle(color="#37DCC9", size=95).encode(
        tooltip=[
            alt.Tooltip("Month:N", title="Month"),
            alt.Tooltip("Revenue:Q", title="Revenue (€)", format=",.2f"),
        ]
    )
    labels = base.mark_text(
        align="center",
        baseline="bottom",
        dy=-12,
        fontSize=13,
        fontWeight="bold",
        color="#DFFCF6",
        tooltip=False,
    ).encode(text=alt.Text("RevenueLabel:N"))

    chart = alt.layer(line, dots, labels).properties(height=295)
    return style_chart(chart)


def segment_chart(breakdowns, dimension):
    months = sorted(breakdowns)[-2:]
    latest = breakdowns[months[-1]].get(dimension, {})
    names = sorted(
        {name for month in months for name in breakdowns[month].get(dimension, {})},
        key=lambda name: (-latest.get(name, 0), name),
    )
    rows = [
        {
            "Segment": name,
            "Month": month,
            "Revenue": breakdowns[month].get(dimension, {}).get(name, 0),
        }
        for month in months
        for name in names
    ]
    df = pd.DataFrame(rows)
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("Revenue:Q", title="Revenue (€)", axis=alt.Axis(format="~s")),
            y=alt.Y("Segment:N", title=None, sort=names),
            yOffset=alt.YOffset("Month:N", sort=months),
            color=alt.Color(
                "Month:N",
                title=None,
                scale=alt.Scale(domain=months, range=["#8299B6", "#37DCC9"]),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("Segment:N"),
                alt.Tooltip("Month:N"),
                alt.Tooltip("Revenue:Q", title="Revenue (€)", format=",.2f"),
            ],
        )
        .properties(height=305)
    )
    return style_chart(chart)


@st.dialog("CSV input template", width="large")
def show_csv_template():
    """Show the required CSV layout as a blank table."""
    st.caption("Use these exact column headers when preparing your sales CSV.")
    # This is a reference schema, not an interactive data grid.
    headers = "".join(
        f'<th scope="col" style="padding:10px 9px; text-align:left; '
        'font-weight:400; color:#B7C7DA; border:1px solid #25374D; '
        f'white-space:nowrap;">{escape(column)}</th>'
        for column in CSV_COLUMNS
    )
    empty_cells = "".join(
        '<td style="height:29px; padding:0; border:1px solid #25374D;">&nbsp;</td>'
        for _ in CSV_COLUMNS
    )
    st.markdown(
        # Put the rounded border on the table itself. Streamlit may add
        # space after a Markdown table; a bordered wrapper made that space
        # look like an extra empty row beneath the two intended blank rows.
        '<div style="overflow-x:auto;">'
        '<table style="width:100%; min-width:1000px; border-collapse:separate; '
        'border-spacing:0; border:1px solid #25374D; border-radius:9px; '
        'overflow:hidden; background:#0C1829; font-size:14px; '
        'margin:0 !important;">'
        f'<thead><tr style="background:#112035;">{headers}</tr></thead>'
        f'<tbody><tr>{empty_cells}</tr><tr>{empty_cells}</tr></tbody>'
        '</table></div>',
        unsafe_allow_html=True,
        anchors=False,
    )
    st.caption(
        "Date: YYYY-MM-DD  ·  Quantity: positive whole number  ·  Discount: 0–100"
    )
    st.caption(
        "Unit price and total sales: non-negative numbers (decimals allowed). "
        "Other fields: non-empty text."
    )
    st.download_button(
        "Download blank CSV template",
        data=",".join(CSV_COLUMNS) + "\n",
        file_name="sales_template.csv",
        mime="text/csv",
        use_container_width=False,
    )


def clear_previous_report():
    """Reset the report when the selected CSV changes or is removed."""
    st.session_state.pop("report_data", None)
    st.session_state.pop("report_signature", None)
    st.session_state.pop("report_filename", None)
    st.session_state.pop("report_created_at", None)


# Use Streamlit's native single-file uploader, which supplies both the
# built-in × remove control and a direct file-picker replacement action.
# CSS changes only the appearance of its native '+' upload control.


# Sidebar: prominent upload workflow and readable navigation.
with st.sidebar:
    st.markdown(
        '<div class="si-brand">'
        '<div class="si-brand-icon">◈</div>'
        '<div><div class="si-brand-title">Sales Intelligence</div>'
        '<div class="si-brand-caption">AI Business Report Studio</div></div></div>',
        unsafe_allow_html=True,
        anchors=False,
    )
    st.divider()
    st.markdown(
        '<div class="si-sidebar-label">NEW REPORT</div>',
        unsafe_allow_html=True,
        anchors=False,
    )
    st.markdown(
        '<div class="si-sidebar-description">Upload a sales CSV to generate '
        "a clear business report with insights and charts.</div>",
        unsafe_allow_html=True,
        anchors=False,
    )
    # The native uploader provides a real × remove control and reopens the
    # operating-system file picker when its small add/replace control is clicked.
    # In single-file mode, choosing another CSV replaces the existing one.
    uploaded_file = st.file_uploader(
        "Sales CSV file",
        type=["csv"],
        accept_multiple_files=False,
        key="sales_csv_file",
        on_change=clear_previous_report,
    )
    file_content = uploaded_file.getvalue() if uploaded_file is not None else None
    filename = uploaded_file.name if uploaded_file is not None else None
    signature = (
        hashlib.sha256(filename.encode() + b"\0" + file_content).hexdigest()
        if file_content is not None
        else None
    )
    generate_clicked = st.button(
        "✦  Generate Report",
        type="primary",
        use_container_width=True,
        disabled=uploaded_file is None,
    )

    generation_succeeded = False
    if generate_clicked:
        st.session_state["report_data"] = None
        st.session_state["report_signature"] = None
        with st.spinner("Analyzing sales data and generating the report..."):
            try:
                response = requests.post(
                    API_URL,
                    files={"file": (filename, file_content, "text/csv")},
                    timeout=120,
                )
                if response.status_code == 422:
                    st.error(str(response.json().get("detail", "Invalid CSV file.")))
                elif not response.ok:
                    st.error(f"Report request failed (HTTP {response.status_code}).")
                else:
                    st.session_state["report_data"] = response.json()
                    st.session_state["report_signature"] = signature
                    st.session_state["report_filename"] = filename
                    st.session_state["report_created_at"] = (
                        datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")
                    )
                    generation_succeeded = True
            except requests.exceptions.RequestException:
                st.error(
                    "Cannot reach FastAPI. Start the backend at http://127.0.0.1:8000."
                )
            except ValueError:
                st.error("The backend returned an invalid response.")

        if generation_succeeded:
            # Restore the notification to its original sidebar position.
            success_message = st.empty()
            success_message.success("Report generated successfully.")
            time.sleep(2)
            success_message.empty()

    st.divider()
    st.markdown(
        '<div class="si-sidebar-label">HOW TO USE</div>',
        unsafe_allow_html=True,
        anchors=False,
    )
    st.markdown(
        '<div class="si-sidebar-note">'
        "<strong>1</strong> &nbsp;Upload your sales CSV file.<br>"
        "<strong>2</strong> &nbsp;Click Generate Report to view your results."
        "</div>",
        unsafe_allow_html=True,
        anchors=False,
    )
    if st.button("View CSV input template", use_container_width=True):
        show_csv_template()


# Hero: visible both before and after uploading.
st.markdown(
    '<div class="si-hero">'
    '<div class="si-eyebrow">Business Report Generator</div>'
    '<div class="si-hero-title" role="heading" aria-level="1">'
    "Business clarity, from your data.</div>"
    "<p>Turn your sales CSV into a validated performance overview, "
    "an evidence-based AI report, and interactive revenue analytics.</p>"
    "</div>",
    unsafe_allow_html=True,
    anchors=False,
)

report = st.session_state.get("report_data")
if report is not None and signature != st.session_state.get("report_signature"):
    report = None
    st.info(
        "The selected file has changed. Generate a report for this file to continue."
    )

if report is None:
    st.markdown(
        '<div class="si-empty">'
        '<div class="si-eyebrow">READY WHEN YOU ARE</div>'
        "<h3>Your next business report starts here</h3>"
        "<p>Choose a CSV in the sidebar, and then select <strong>Generate Report</strong>. "
        "Your management report will appear here.</p>"
        "</div>",
        unsafe_allow_html=True,
        anchors=False,
    )
    st.stop()

monthly = report.get("monthly_kpis", [])
comparisons = report.get("comparisons", [])
breakdowns = report.get("revenue_breakdowns", {})
ai_report = report.get("ai_report")
if not monthly:
    st.error("The backend returned no monthly KPIs.")
    st.stop()
latest = monthly[-1]

st.markdown(
    '<div class="si-report-heading">'
    + (
        '<div class="si-report-status"><span class="si-report-status-dot"></span>'
        "Report is ready</div>"
        if report.get("narrative_generated") and ai_report
        else '<div class="si-report-status si-report-status-muted">'
        "Verified metrics available</div>"
    )
    + "<h2>Business Performance Report</h2>"
    '<div class="si-report-sub">'
    f"Source: {escape(st.session_state.get('report_filename', 'CSV upload'))}"
    f" &nbsp; · &nbsp; Period: {escape(month_label(monthly[0]['month']))}"
    f" – {escape(month_label(latest['month']))}"
    " &nbsp; · &nbsp; EUR</div></div>",
    unsafe_allow_html=True,
    anchors=False,
)

# Download uses the existing API response; it does not rerun analytics or the LLM.
try:
    pdf_bytes = build_report_pdf(
        report,
        source_filename=st.session_state.get("report_filename", "sales.csv"),
        generated_at=st.session_state.get("report_created_at", ""),
    )
    st.download_button(
        "↓  Download PDF Report",
        data=pdf_bytes,
        file_name=(
            f"business_report_{monthly[0]['month']}_to_{latest['month']}.pdf"
        ),
        mime="application/pdf",
        type="secondary",
        on_click="ignore",
    )
except Exception:
    st.warning("PDF export is temporarily unavailable; the report is still accessible below.")


section_heading("AI Management Report")
if report.get("narrative_generated") and ai_report:
    st.markdown(
        '<div class="si-summary">'
        '<div class="si-card-kicker">✦ &nbsp; EXECUTIVE SUMMARY</div>'
        f"<p>{escape(ai_report['executive_summary'])}</p>"
        "</div>",
        unsafe_allow_html=True,
        anchors=False,
    )
    left, right = st.columns(2, gap="medium")
    with left:
        report_list_card("Key Insights", ai_report.get("key_insights", []), "insights")
    with right:
        report_list_card(
            "Notable Changes", ai_report.get("notable_changes", []), "changes"
        )
else:
    st.warning(
        "The AI narrative is temporarily unavailable. "
        "Verified KPIs and charts remain accessible below."
    )

section_heading(
    "Performance Snapshot", "Latest month · compared with the previous reporting period"
)
items = [
    (
        "Total Revenue",
        money(latest["total_revenue"]),
        percent_delta(comparisons, "total_revenue"),
        "€",
    ),
    (
        "Order Count",
        f"{int(latest['order_count']):,}",
        percent_delta(comparisons, "order_count"),
        "#",
    ),
    (
        "Units Sold",
        f"{int(latest['units_sold']):,}",
        percent_delta(comparisons, "units_sold"),
        "◈",
    ),
    (
        "Average Order Value",
        money(latest["average_order_value"]),
        percent_delta(comparisons, "average_order_value"),
        "€",
    ),
    (
        "Revenue per Unit",
        money(latest["revenue_per_unit"]),
        percent_delta(comparisons, "revenue_per_unit"),
        "€",
    ),
    (
        "MoM Revenue Growth",
        f"{latest['revenue_growth_pct']:+.2f}%"
        if latest.get("revenue_growth_pct") is not None
        else "N/A",
        None,
        "%",
    ),
]

# MoM revenue growth IS itself the latest month-to-month comparison.
# Do not display the unrelated generic "No prior comparison" placeholder.
if len(monthly) >= 2 and latest.get("revenue_growth_pct") is not None:
    growth_note = (
        f"{month_label(monthly[-2]['month'])} → {month_label(latest['month'])}"
    )
else:
    growth_note = "A second month is required"

# Use an HTML grid so the tiles keep consistent heights at different widths.
st.markdown(
    '<div class="si-kpi-grid">'
    + "".join(
        kpi_card(
            label,
            value,
            delta,
            icon,
            note=growth_note if label == "MoM Revenue Growth" else None,
        )
        for label, value, delta, icon in items
    )
    + "</div>",
    unsafe_allow_html=True,
    anchors=False,
)

section_heading("Revenue Analytics")
with st.container(key="revenue-chart"):
    st.markdown(
        '<div class="si-chart-title">Monthly Revenue Trend</div>'
        '<div class="si-chart-sub">Revenue across the reporting period</div>',
        unsafe_allow_html=True,
        anchors=False,
    )
    st.altair_chart(revenue_trend_chart(monthly), width="stretch", theme=None)

if breakdowns:
    cat_col, reg_col = st.columns(2, gap="medium")
    with cat_col:
        with st.container(key="category-chart"):
            st.markdown(
                '<div class="si-chart-title">Revenue by Category</div>'
                '<div class="si-chart-sub">Latest two months compared</div>',
                unsafe_allow_html=True,
                anchors=False,
            )
            st.altair_chart(
                segment_chart(breakdowns, "category"), width="stretch", theme=None
            )
    with reg_col:
        with st.container(key="region-chart"):
            st.markdown(
                '<div class="si-chart-title">Revenue by Region</div>'
                '<div class="si-chart-sub">Latest two months compared</div>',
                unsafe_allow_html=True,
                anchors=False,
            )
            st.altair_chart(
                segment_chart(breakdowns, "region"), width="stretch", theme=None
            )

st.markdown(
    '<div class="si-bottom">Built for clearer business decisions'
    '<span class="si-footer-separator"> · </span>'
    "Evidence-based reporting from your sales data</div>",
    unsafe_allow_html=True,
    anchors=False,
)
