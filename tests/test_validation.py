import pandas as pd
import pytest

from backend.app.analytics.validator import validate_sales_data


def create_sample_data():
    return pd.DataFrame(
        [
            {
                "order_id": "ORD-001",
                "date": "2026-08-01",
                "customer_id": "C-001",
                "product": "Webcam",
                "category": "Electronics",
                "region": "North",
                "quantity": 2,
                "unit_price": 50,
                "discount_pct": 10,
                "total_sales": 90,
            }
        ]
    )


def test_valid_columns():
    df = create_sample_data()

    assert validate_sales_data(df) is None


def test_missing_column():
    df = create_sample_data()
    df = df.drop(columns=["total_sales"])

    with pytest.raises(ValueError, match="Missing required columns: total_sales"):
        validate_sales_data(df)


def test_invalid_numeric_value():
    df = create_sample_data()
    df["quantity"] = ["INVALID"]

    with pytest.raises(
        ValueError, match="Column 'quantity' contains missing or non-numeric values"
    ):
        validate_sales_data(df)


def test_invalid_date():
    df = create_sample_data()
    df["date"] = ["2026-02-30"]

    with pytest.raises(
        ValueError, match="Column 'date' contains missing or invalid dates"
    ):
        validate_sales_data(df)


def test_invalid_date_format():
    df = create_sample_data()
    df["date"] = ["2026/08/01"]

    with pytest.raises(
        ValueError, match="Column 'date' contains missing or invalid dates"
    ):
        validate_sales_data(df)


def test_zero_quantity():
    df = create_sample_data()
    df["quantity"] = [0]

    with pytest.raises(
        ValueError, match="Column 'quantity' must contain positive whole numbers"
    ):
        validate_sales_data(df)


def test_decimal_quantity():
    df = create_sample_data()
    df["quantity"] = [2.5]

    with pytest.raises(
        ValueError, match="Column 'quantity' must contain positive whole numbers"
    ):
        validate_sales_data(df)


def test_negative_unit_price():
    df = create_sample_data()
    df["unit_price"] = [-50]

    with pytest.raises(
        ValueError, match="Column 'unit_price' cannot contain negative values"
    ):
        validate_sales_data(df)


def test_invalid_discount():
    df = create_sample_data()
    df["discount_pct"] = [150]

    with pytest.raises(
        ValueError, match="Column 'discount_pct' must be between 0 and 100"
    ):
        validate_sales_data(df)


def test_negative_total_sales():
    df = create_sample_data()
    df["total_sales"] = [-90]

    with pytest.raises(
        ValueError, match="Column 'total_sales' cannot contain negative values"
    ):
        validate_sales_data(df)


def test_infinite_value():
    df = create_sample_data()
    df["unit_price"] = [float("inf")]

    with pytest.raises(
        ValueError, match="Column 'unit_price' contains infinite values"
    ):
        validate_sales_data(df)


# Tests for required text fields


@pytest.mark.parametrize("invalid_value", ["", "   ", None])
def test_missing_or_blank_product(invalid_value):
    df = create_sample_data()
    df["product"] = [invalid_value]

    with pytest.raises(
        ValueError, match="Column 'product' contains missing or blank values"
    ):
        validate_sales_data(df)


def test_literal_word_empty_is_allowed():
    df = create_sample_data()
    df["product"] = ["empty"]

    assert validate_sales_data(df) is None


# Tests for revenue consistency


def test_inconsistent_revenue():
    df = create_sample_data()

    df["quantity"] = [3]
    df["unit_price"] = [100]
    df["discount_pct"] = [10]
    df["total_sales"] = [350]

    with pytest.raises(ValueError, match="Row 2: Revenue inconsistency"):
        validate_sales_data(df)


def test_revenue_rounding_tolerance():
    df = create_sample_data()

    df["total_sales"] = [90.01]

    assert validate_sales_data(df) is None
