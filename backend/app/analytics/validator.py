import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
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
}

TEXT_COLUMNS = [
    "order_id",
    "customer_id",
    "product",
    "category",
    "region",
]

NUMERIC_COLUMNS = [
    "quantity",
    "unit_price",
    "discount_pct",
    "total_sales",
]


def validate_sales_data(df: pd.DataFrame) -> None:
    """Validate the structure and values of sales data."""

    # Check for missing required columns
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")

    # Check whether the dataset contains any rows
    if df.empty:
        raise ValueError("The CSV file contains no data rows.")

    # Check required text columns
    for column in TEXT_COLUMNS:
        values = df[column].astype("string")

        if values.isna().any() or values.str.strip().eq("").any():
            raise ValueError(f"Column '{column}' contains missing or blank values.")

    # Check date format (YYYY-MM-DD)
    valid_format = (
        df["date"].astype("string").str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False)
    )

    # Check whether dates actually exist
    valid_dates = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce").notna()

    if not (valid_format & valid_dates).all():
        raise ValueError(
            "Column 'date' contains missing or invalid dates. "
            "Expected format: YYYY-MM-DD."
        )

    # Check numeric columns
    numeric_data = {}

    for column in NUMERIC_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")

        if values.isna().any():
            raise ValueError(
                f"Column '{column}' contains missing or non-numeric values."
            )

        if not np.isfinite(values).all():
            raise ValueError(f"Column '{column}' contains infinite values.")

        numeric_data[column] = values

    # Quantity must be a positive whole number
    quantity = numeric_data["quantity"]

    if (quantity <= 0).any() or (quantity % 1 != 0).any():
        raise ValueError("Column 'quantity' must contain positive whole numbers.")

    # Unit price cannot be negative
    if (numeric_data["unit_price"] < 0).any():
        raise ValueError("Column 'unit_price' cannot contain negative values.")

    # Discount percentage must be between 0 and 100
    discount = numeric_data["discount_pct"]

    if ((discount < 0) | (discount > 100)).any():
        raise ValueError("Column 'discount_pct' must be between 0 and 100.")

    # Total sales cannot be negative
    actual_sales = numeric_data["total_sales"]

    if (actual_sales < 0).any():
        raise ValueError("Column 'total_sales' cannot contain negative values.")

    # Check revenue consistency
    expected_sales = (
        quantity * numeric_data["unit_price"] * (1 - discount / 100)
    ).round(2)

    # Allow a difference of up to 0.01 for rounding
    matches = np.isclose(actual_sales, expected_sales, rtol=0, atol=0.010001)

    inconsistent_rows = np.flatnonzero(~matches)

    if len(inconsistent_rows) > 0:
        position = int(inconsistent_rows[0])

        # CSV header is row 1, so data starts at row 2
        csv_row = position + 2

        expected = expected_sales.iloc[position]
        actual = actual_sales.iloc[position]

        raise ValueError(
            f"Row {csv_row}: Revenue inconsistency. "
            f"Expected total_sales: {expected:.2f}; "
            f"found: {actual:.2f}."
        )
