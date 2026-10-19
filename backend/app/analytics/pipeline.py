from io import BytesIO

import pandas as pd

from .validator import validate_sales_data
from .metrics import (
    calculate_monthly_kpis,
    calculate_monthly_comparisons,
    calculate_revenue_breakdowns,
    find_top_revenue_product,
    calculate_report_highlights,
)
from .insights import detect_notable_changes


def analyze_sales_data(df: pd.DataFrame) -> dict:
    """Validate sales data and perform the complete analysis."""

    # Step 1: Validate the dataset
    validate_sales_data(df)

    # Step 2: Calculate monthly KPIs
    monthly_kpis = calculate_monthly_kpis(df)

    # Step 3: Compare consecutive months
    comparisons = calculate_monthly_comparisons(monthly_kpis)

    # Step 4: Calculate revenue breakdowns
    breakdowns = calculate_revenue_breakdowns(df)

    # Step 5: Identify the top-revenue product
    top_product = find_top_revenue_product(breakdowns)

    # Step 6: Detect notable business changes
    notable_changes = detect_notable_changes(
        monthly_kpis,
        comparisons,
        breakdowns,
    )

    # Step 7: Calculate full-period highlights for grounded AI reporting
    report_highlights = calculate_report_highlights(df, monthly_kpis, comparisons)

    # Return the complete analysis
    return {
        "monthly_kpis": monthly_kpis,
        "comparisons": comparisons,
        "revenue_breakdowns": breakdowns,
        "top_revenue_product": top_product,
        "notable_changes": notable_changes,
        "report_highlights": report_highlights,
    }


def analyze_csv_bytes(csv_content: bytes) -> dict:
    """Read uploaded CSV content and run the analytical workflow."""

    if not csv_content or not csv_content.strip():
        raise ValueError("The uploaded CSV file is empty.")

    try:
        df = pd.read_csv(
            BytesIO(csv_content),
            encoding="utf-8-sig",
        )

    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        UnicodeDecodeError,
    ) as error:
        raise ValueError(
            "Could not read the CSV file. Please provide a valid UTF-8 CSV file."
        ) from error

    return analyze_sales_data(df)
