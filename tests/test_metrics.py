import pandas as pd

from backend.app.analytics.validator import validate_sales_data
from backend.app.analytics.metrics import (
    calculate_monthly_kpis,
    calculate_monthly_comparisons,
    calculate_revenue_breakdowns,
    find_top_revenue_product,
)


def create_sample_data():
    """Create a small dataset with known expected results."""

    return pd.DataFrame(
        [
            {
                "order_id": "ORD-001",
                "date": "2026-08-01",
                "customer_id": "C-001",
                "product": "Webcam",
                "category": "Electronics",
                "region": "North",
                "quantity": 1,
                "unit_price": 100,
                "discount_pct": 0,
                "total_sales": 100,
            },
            {
                "order_id": "ORD-002",
                "date": "2026-08-15",
                "customer_id": "C-002",
                "product": "Mouse",
                "category": "Accessories",
                "region": "South",
                "quantity": 2,
                "unit_price": 50,
                "discount_pct": 10,
                "total_sales": 90,
            },
            {
                "order_id": "ORD-003",
                "date": "2026-09-05",
                "customer_id": "C-003",
                "product": "Keyboard",
                "category": "Accessories",
                "region": "North",
                "quantity": 4,
                "unit_price": 50,
                "discount_pct": 0,
                "total_sales": 200,
            },
        ]
    )


def test_monthly_kpis():
    df = create_sample_data()
    validate_sales_data(df)

    results = calculate_monthly_kpis(df)

    august = results[0]
    september = results[1]

    assert len(results) == 2

    # August
    assert august["month"] == "2026-08"
    assert august["total_revenue"] == 190
    assert august["order_count"] == 2
    assert august["units_sold"] == 3
    assert august["average_order_value"] == 95
    assert august["revenue_per_unit"] == 63.33
    assert august["revenue_growth_pct"] is None

    # September
    assert september["month"] == "2026-09"
    assert september["total_revenue"] == 200
    assert september["order_count"] == 1
    assert september["units_sold"] == 4
    assert september["average_order_value"] == 200
    assert september["revenue_per_unit"] == 50
    assert september["revenue_growth_pct"] == 5.26


def test_monthly_comparisons():
    df = create_sample_data()
    validate_sales_data(df)

    monthly_kpis = calculate_monthly_kpis(df)
    comparisons = calculate_monthly_comparisons(monthly_kpis)

    assert len(comparisons) == 1

    comparison = comparisons[0]

    assert comparison["from_month"] == "2026-08"
    assert comparison["to_month"] == "2026-09"

    changes = comparison["changes"]

    # Revenue
    assert changes["total_revenue"]["absolute_change"] == 10
    assert changes["total_revenue"]["percentage_change"] == 5.26

    # Orders
    assert changes["order_count"]["absolute_change"] == -1
    assert changes["order_count"]["percentage_change"] == -50

    # Units sold
    assert changes["units_sold"]["absolute_change"] == 1
    assert changes["units_sold"]["percentage_change"] == 33.33

    # Average order value
    assert changes["average_order_value"]["absolute_change"] == 105
    assert changes["average_order_value"]["percentage_change"] == 110.53

    # Revenue per unit
    assert changes["revenue_per_unit"]["absolute_change"] == -13.33
    assert changes["revenue_per_unit"]["percentage_change"] == -21.05


def test_revenue_breakdowns():
    df = create_sample_data()
    validate_sales_data(df)

    breakdowns = calculate_revenue_breakdowns(df)

    august = breakdowns["2026-08"]
    september = breakdowns["2026-09"]

    # Category
    assert august["category"]["Electronics"] == 100
    assert august["category"]["Accessories"] == 90
    assert september["category"]["Accessories"] == 200

    # Region
    assert august["region"]["North"] == 100
    assert august["region"]["South"] == 90
    assert september["region"]["North"] == 200

    # Product
    assert august["product"]["Webcam"] == 100
    assert august["product"]["Mouse"] == 90
    assert september["product"]["Keyboard"] == 200

    # All category revenue must sum to total revenue
    assert sum(august["category"].values()) == 190
    assert sum(september["category"].values()) == 200


def test_top_revenue_product():
    df = create_sample_data()
    validate_sales_data(df)

    breakdowns = calculate_revenue_breakdowns(df)
    result = find_top_revenue_product(breakdowns)

    assert result == {
        "month": "2026-09",
        "product": "Keyboard",
        "revenue": 200.0,
    }


def test_top_revenue_product_tie():
    breakdowns = {
        "2026-09": {
            "product": {
                "Webcam": 200.0,
                "Keyboard": 200.0,
                "Mouse": 100.0,
            }
        }
    }

    result = find_top_revenue_product(breakdowns)

    assert result["product"] == "Keyboard"
    assert result["revenue"] == 200.0


def test_top_revenue_product_empty():
    result = find_top_revenue_product({})

    assert result is None


def test_three_month_comparisons():
    df = create_sample_data()

    # Add a July transaction
    july_row = {
        "order_id": "ORD-000",
        "date": "2026-07-10",
        "customer_id": "C-000",
        "product": "Webcam",
        "category": "Electronics",
        "region": "North",
        "quantity": 1,
        "unit_price": 50,
        "discount_pct": 0,
        "total_sales": 50,
    }

    df = pd.concat([df, pd.DataFrame([july_row])], ignore_index=True)

    validate_sales_data(df)

    monthly_kpis = calculate_monthly_kpis(df)
    comparisons = calculate_monthly_comparisons(monthly_kpis)

    assert len(monthly_kpis) == 3
    assert len(comparisons) == 2

    assert comparisons[0]["from_month"] == "2026-07"
    assert comparisons[0]["to_month"] == "2026-08"

    assert comparisons[1]["from_month"] == "2026-08"
    assert comparisons[1]["to_month"] == "2026-09"
