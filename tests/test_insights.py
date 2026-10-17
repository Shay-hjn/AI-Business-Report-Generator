from backend.app.analytics.metrics import calculate_monthly_comparisons
from backend.app.analytics.insights import detect_notable_changes


def make_kpi(month, revenue, orders=100, units=200):
    """Create monthly KPI data for testing."""

    return {
        "month": month,
        "total_revenue": revenue,
        "order_count": orders,
        "units_sold": units,
        "average_order_value": round(revenue / orders, 2),
        "revenue_per_unit": round(revenue / units, 2),
        "revenue_growth_pct": None,
    }


def analyze(monthly_kpis, breakdowns=None):
    """Run the notable change detector with calculated comparisons."""

    comparisons = calculate_monthly_comparisons(monthly_kpis)

    if breakdowns is None:
        breakdowns = {
            kpi["month"]: {
                "category": {},
                "region": {},
                "product": {},
            }
            for kpi in monthly_kpis
        }

    return detect_notable_changes(
        monthly_kpis,
        comparisons,
        breakdowns,
    )


def test_significant_revenue_growth():
    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 12500),
    ]

    findings = analyze(monthly_kpis)

    assert len(findings) == 1
    assert findings[0]["type"] == "overall_revenue_change"
    assert findings[0]["percentage_change"] == 25.0
    assert findings[0]["absolute_change"] == 2500


def test_small_revenue_change_is_ignored():
    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 11000),
    ]

    findings = analyze(monthly_kpis)

    assert findings == []


def test_category_and_regional_changes():
    """Detect opposing movements even when overall revenue is stable."""

    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 10000),
    ]

    breakdowns = {
        "2026-08": {
            "category": {
                "Electronics": 6000,
                "Furniture": 4000,
            },
            "region": {
                "North": 5000,
                "South": 5000,
            },
            "product": {},
        },
        "2026-09": {
            "category": {
                "Electronics": 3000,
                "Furniture": 7000,
            },
            "region": {
                "North": 500,
                "South": 9500,
            },
            "product": {},
        },
    }

    findings = analyze(monthly_kpis, breakdowns)

    types = [item["type"] for item in findings]

    assert types.count("category_revenue_change") == 2
    assert types.count("region_revenue_change") == 2
    assert "overall_revenue_change" not in types

    north = next(item for item in findings if item.get("name") == "North")

    assert north["percentage_change"] == -90.0


def test_significant_product_spike():
    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 10000),
    ]

    breakdowns = {
        "2026-08": {
            "product": {"Webcam": 1000, "Other": 9000},
        },
        "2026-09": {
            "product": {"Webcam": 4000, "Other": 6000},
        },
    }

    findings = analyze(monthly_kpis, breakdowns)

    spikes = [item for item in findings if item["type"] == "product_revenue_spike"]

    assert len(spikes) == 1
    assert spikes[0]["name"] == "Webcam"
    assert spikes[0]["percentage_change"] == 300.0
    assert spikes[0]["absolute_change"] == 3000


def test_small_product_spike_is_ignored():
    """A high percentage alone should not trigger a finding."""

    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 10000),
    ]

    breakdowns = {
        "2026-08": {
            "product": {"Webcam": 100, "Other": 9900},
        },
        "2026-09": {
            "product": {"Webcam": 600, "Other": 9400},
        },
    }

    findings = analyze(monthly_kpis, breakdowns)

    assert not any(item["type"] == "product_revenue_spike" for item in findings)


def test_new_product_revenue():
    """New revenue activity should not produce an invented growth rate."""

    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 10000),
    ]

    breakdowns = {
        "2026-08": {
            "product": {"Other": 10000},
        },
        "2026-09": {
            "product": {"Other": 8000, "New Product": 2000},
        },
    }

    findings = analyze(monthly_kpis, breakdowns)

    new_product = next(
        item for item in findings if item["type"] == "new_product_revenue"
    )

    assert new_product["name"] == "New Product"
    assert new_product["percentage_change"] is None
    assert new_product["absolute_change"] == 2000


def test_revenue_volume_divergence():
    monthly_kpis = [
        make_kpi("2026-08", 10000, orders=100, units=200),
        make_kpi("2026-09", 8000, orders=130, units=250),
    ]

    findings = analyze(monthly_kpis)

    divergence = next(
        item for item in findings if item["type"] == "revenue_volume_divergence"
    )

    assert divergence["revenue_change_pct"] == -20.0
    assert divergence["order_count_change_pct"] == 30.0
    assert divergence["units_sold_change_pct"] == 25.0


def test_three_month_detection():
    monthly_kpis = [
        make_kpi("2026-07", 10000),
        make_kpi("2026-08", 13000),
        make_kpi("2026-09", 9000),
    ]

    findings = analyze(monthly_kpis)

    revenue_findings = [
        item for item in findings if item["type"] == "overall_revenue_change"
    ]

    assert len(revenue_findings) == 2

    assert revenue_findings[0]["from_month"] == "2026-07"
    assert revenue_findings[0]["to_month"] == "2026-08"
    assert revenue_findings[0]["percentage_change"] == 30.0

    assert revenue_findings[1]["from_month"] == "2026-08"
    assert revenue_findings[1]["to_month"] == "2026-09"
    assert revenue_findings[1]["percentage_change"] == -30.77


def test_no_comparison_for_single_month():
    monthly_kpis = [
        make_kpi("2026-08", 10000),
    ]

    findings = analyze(monthly_kpis)

    assert findings == []


def test_zero_previous_revenue():
    monthly_kpis = [
        make_kpi("2026-08", 0),
        make_kpi("2026-09", 5000),
    ]

    findings = analyze(monthly_kpis)

    assert len(findings) == 1
    assert findings[0]["type"] == "revenue_started"
    assert findings[0]["percentage_change"] is None


def test_segment_findings_are_limited():
    """Keep only the two largest category changes."""

    monthly_kpis = [
        make_kpi("2026-08", 10000),
        make_kpi("2026-09", 10000),
    ]

    breakdowns = {
        "2026-08": {
            "category": {
                "A": 4000,
                "B": 3000,
                "C": 2000,
                "D": 1000,
            },
        },
        "2026-09": {
            "category": {
                "A": 1000,
                "B": 5000,
                "C": 3500,
                "D": 500,
            },
        },
    }

    findings = analyze(monthly_kpis, breakdowns)

    category_findings = [
        item for item in findings if item["type"] == "category_revenue_change"
    ]

    assert len(category_findings) == 2
    assert [item["name"] for item in category_findings] == ["A", "B"]
