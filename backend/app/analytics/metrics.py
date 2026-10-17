import pandas as pd


COMPARISON_METRICS = [
    "total_revenue",
    "order_count",
    "units_sold",
    "average_order_value",
    "revenue_per_unit",
]

BREAKDOWN_DIMENSIONS = [
    "category",
    "region",
    "product",
]


def calculate_monthly_kpis(df: pd.DataFrame) -> list[dict]:
    """Calculate business KPIs for each month in a validated dataset."""

    # Work with a copy of the original data
    sales = df.copy()

    # Extract the reporting month
    sales["month"] = pd.to_datetime(sales["date"], format="%Y-%m-%d").dt.strftime(
        "%Y-%m"
    )

    sales["quantity"] = pd.to_numeric(sales["quantity"])
    sales["total_sales"] = pd.to_numeric(sales["total_sales"])

    results = []
    previous_revenue = None

    # Calculate KPIs for each month
    for month, monthly_data in sales.groupby("month", sort=True):
        revenue = round(float(monthly_data["total_sales"].sum()), 2)
        order_count = int(monthly_data["order_id"].nunique())
        units_sold = int(monthly_data["quantity"].sum())

        average_order_value = round(revenue / order_count, 2)
        revenue_per_unit = round(revenue / units_sold, 2)

        # Compare revenue with the previous month
        if previous_revenue is None or previous_revenue == 0:
            revenue_growth_pct = None
        else:
            revenue_growth_pct = round(
                ((revenue - previous_revenue) / previous_revenue) * 100, 2
            )

        results.append(
            {
                "month": month,
                "total_revenue": revenue,
                "order_count": order_count,
                "units_sold": units_sold,
                "average_order_value": average_order_value,
                "revenue_per_unit": revenue_per_unit,
                "revenue_growth_pct": revenue_growth_pct,
            }
        )

        previous_revenue = revenue

    return results


def calculate_monthly_comparisons(monthly_kpis: list[dict]) -> list[dict]:
    """Compare KPIs between consecutive reporting months."""

    comparisons = []

    for previous, current in zip(monthly_kpis, monthly_kpis[1:]):
        changes = {}

        for metric in COMPARISON_METRICS:
            previous_value = previous[metric]
            current_value = current[metric]

            absolute_change = round(current_value - previous_value, 2)

            if previous_value == 0:
                percentage_change = None
            else:
                percentage_change = round(
                    (current_value - previous_value) / previous_value * 100, 2
                )

            changes[metric] = {
                "absolute_change": absolute_change,
                "percentage_change": percentage_change,
            }

        comparisons.append(
            {
                "from_month": previous["month"],
                "to_month": current["month"],
                "changes": changes,
            }
        )

    return comparisons


def calculate_revenue_breakdowns(df: pd.DataFrame) -> dict:
    """Calculate monthly revenue by category, region, and product."""

    sales = df.copy()

    sales["month"] = pd.to_datetime(sales["date"], format="%Y-%m-%d").dt.strftime(
        "%Y-%m"
    )

    sales["total_sales"] = pd.to_numeric(sales["total_sales"])

    breakdowns = {}

    for month, monthly_data in sales.groupby("month", sort=True):
        breakdowns[month] = {}

        for dimension in BREAKDOWN_DIMENSIONS:
            revenue_by_group = monthly_data.groupby(dimension)["total_sales"].sum()

            breakdowns[month][dimension] = {
                str(name): round(float(revenue), 2)
                for name, revenue in revenue_by_group.items()
            }

    return breakdowns


def find_top_revenue_product(breakdowns: dict) -> dict | None:
    """Find the highest-revenue product in the latest month."""

    if not breakdowns:
        return None

    latest_month = max(breakdowns)
    products = breakdowns[latest_month].get("product", {})

    if not products:
        return None

    # Sort by highest revenue, then alphabetically for ties
    top_product, top_revenue = sorted(
        products.items(), key=lambda item: (-item[1], item[0])
    )[0]

    return {
        "month": latest_month,
        "product": top_product,
        "revenue": top_revenue,
    }
