"""Verified highlights and reporting scope: 1, 2, 3+ months."""
import pandas as pd
from backend.app.analytics.metrics import (
    calculate_monthly_comparisons,
    calculate_monthly_kpis,
    calculate_report_highlights,
)


def rows(monthly_revenues):
    """Small valid-shaped dataset with distinct revenue and unit leaders."""
    result = []
    for month, revenue in monthly_revenues:
        result.extend([
            {"order_id": f"A-{month}", "date": f"{month}-04", "product": "Laptop",
             "quantity": 1, "total_sales": revenue * 0.8},
            {"order_id": f"B-{month}", "date": f"{month}-12", "product": "Cable",
             "quantity": 10, "total_sales": revenue * 0.2},
        ])
    return pd.DataFrame(result)


def highlights_for(data):
    monthly = calculate_monthly_kpis(data)
    comparisons = calculate_monthly_comparisons(monthly)
    return calculate_report_highlights(data, monthly, comparisons)


def test_one_month_has_no_mom_or_historical_extremes():
    info = highlights_for(rows([("2026-01", 100)]))
    assert info["month_count"] == 1
    assert info["overall_revenue_change"] is None
    assert info["highest_revenue_month"] is None
    assert info["lowest_revenue_month"] is None
    assert info["largest_monthly_revenue_increase"] is None
    assert info["largest_monthly_revenue_decrease"] is None
    assert info["top_product_by_revenue_full_period"] == {"product": "Laptop", "revenue": 80}
    assert info["top_product_by_units_full_period"] == {"product": "Cable", "units_sold": 10}


def test_two_months_has_overall_change_but_no_historical_extremes():
    info = highlights_for(rows([("2026-01", 100), ("2026-02", 120)]))
    assert info["month_count"] == 2
    assert info["overall_revenue_change"]["percentage_change"] == 20
    assert info["highest_revenue_month"] is None
    assert info["largest_monthly_revenue_increase"] is None


def test_three_months_detects_extremes_and_directions():
    info = highlights_for(rows([
        ("2026-01", 100), ("2026-02", 180), ("2026-03", 110),
    ]))
    assert info["highest_revenue_month"] == {"months": ["2026-02"], "revenue": 180}
    assert info["lowest_revenue_month"] == {"months": ["2026-01"], "revenue": 100}
    assert info["largest_monthly_revenue_increase"]["absolute_change"] == 80
    assert info["largest_monthly_revenue_increase"]["percentage_change"] == 80
    assert info["largest_monthly_revenue_decrease"]["absolute_change"] == -70
    assert info["overall_revenue_change"]["percentage_change"] == 10


def test_monotonic_and_tied_months_do_not_invent_decreases():
    info = highlights_for(rows([
        ("2026-01", 100), ("2026-02", 100), ("2026-03", 150),
    ]))
    assert info["lowest_revenue_month"]["months"] == ["2026-01", "2026-02"]
    assert info["largest_monthly_revenue_decrease"] is None
    assert info["largest_monthly_revenue_increase"]["absolute_change"] == 50


def test_all_decreases_do_not_invent_an_increase():
    info = highlights_for(rows([
        ("2026-01", 150), ("2026-02", 120), ("2026-03", 100),
    ]))
    assert info["largest_monthly_revenue_increase"] is None
    assert info["largest_monthly_revenue_decrease"]["absolute_change"] == -30


def test_zero_baseline_percentage_is_undefined_not_infinite():
    info = highlights_for(rows([
        ("2026-01", 0), ("2026-02", 100), ("2026-03", 150),
    ]))
    assert info["overall_revenue_change"]["percentage_change"] is None
    assert info["largest_monthly_revenue_increase"]["absolute_change"] == 100
    assert info["largest_monthly_revenue_increase"]["percentage_change"] is None


def test_eight_month_dataset_selects_historical_extremes():
    info = highlights_for(rows([
        ("2026-01", 100), ("2026-02", 120), ("2026-03", 95),
        ("2026-04", 180), ("2026-05", 160), ("2026-06", 220),
        ("2026-07", 190), ("2026-08", 140),
    ]))
    assert info["month_count"] == 8
    assert info["highest_revenue_month"] == {"months": ["2026-06"], "revenue": 220}
    assert info["lowest_revenue_month"] == {"months": ["2026-03"], "revenue": 95}
    assert info["overall_revenue_change"]["percentage_change"] == 40.0
    assert info["largest_monthly_revenue_increase"]["from_month"] == "2026-03"
    assert info["largest_monthly_revenue_increase"]["to_month"] == "2026-04"
    assert info["largest_monthly_revenue_decrease"]["from_month"] == "2026-07"
    assert info["largest_monthly_revenue_decrease"]["to_month"] == "2026-08"
    assert info["top_product_by_revenue_full_period"]["product"] == "Laptop"
    assert info["top_product_by_units_full_period"] == {
        "product": "Cable", "units_sold": 80,
    }
