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


def calculate_report_highlights(
    df: pd.DataFrame, monthly_kpis: list[dict], comparisons: list[dict]
) -> dict:
    """Prepare verified reporting facts; interpretation remains the LLM's job.

    Historical extremes are included only when at least three months are
    present. Rank monthly revenue movements both by absolute EUR change and
    by percentage change: those rankings may identify different month pairs.
    A percentage is undefined when the preceding month's revenue is zero.
    """
    if not monthly_kpis:
        raise ValueError("Cannot calculate report highlights without monthly KPIs.")

    first = monthly_kpis[0]
    last = monthly_kpis[-1]
    month_count = len(monthly_kpis)

    overall_change = None
    if month_count >= 2:
        first_revenue = float(first["total_revenue"])
        last_revenue = float(last["total_revenue"])
        overall_change = {
            "from_month": first["month"],
            "to_month": last["month"],
            "from_revenue": first_revenue,
            "to_revenue": last_revenue,
            "absolute_change": round(last_revenue - first_revenue, 2),
            "percentage_change": (
                round((last_revenue - first_revenue) / first_revenue * 100, 2)
                if first_revenue != 0
                else None
            ),
        }

    highest_month = None
    lowest_month = None
    largest_increase = None
    largest_decrease = None
    largest_percentage_increase = None
    largest_percentage_decrease = None
    if month_count >= 3:
        maximum = max(float(item["total_revenue"]) for item in monthly_kpis)
        minimum = min(float(item["total_revenue"]) for item in monthly_kpis)
        # Report all tied months so the LLM does not invent a unique winner.
        highest_month = {
            "months": [item["month"] for item in monthly_kpis
                       if float(item["total_revenue"]) == maximum],
            "revenue": maximum,
        }
        lowest_month = {
            "months": [item["month"] for item in monthly_kpis
                       if float(item["total_revenue"]) == minimum],
            "revenue": minimum,
        }
        revenue_changes = [
            {
                "from_month": item["from_month"],
                "to_month": item["to_month"],
                **item["changes"]["total_revenue"],
            }
            for item in comparisons
        ]
        increases = [item for item in revenue_changes if item["absolute_change"] > 0]
        decreases = [item for item in revenue_changes if item["absolute_change"] < 0]
        if increases:
            largest_increase = max(increases, key=lambda item: item["absolute_change"])
        if decreases:
            largest_decrease = min(decreases, key=lambda item: item["absolute_change"])

        # A small base can produce a large percentage gain but a modest EUR
        # gain. Keep both rankings explicit rather than conflating them.
        measurable_increases = [
            item for item in increases if item["percentage_change"] is not None
        ]
        measurable_decreases = [
            item for item in decreases if item["percentage_change"] is not None
        ]
        if measurable_increases:
            largest_percentage_increase = max(
                measurable_increases,
                key=lambda item: (item["percentage_change"], item["absolute_change"]),
            )
        if measurable_decreases:
            largest_percentage_decrease = min(
                measurable_decreases,
                key=lambda item: (item["percentage_change"], item["absolute_change"]),
            )

    # Two separate rankings: monetary contribution and units sold. Neither
    # should be mistaken for product popularity or unique buyers.
    totals = (
        df.assign(
            total_sales=pd.to_numeric(df["total_sales"]),
            quantity=pd.to_numeric(df["quantity"]),
        )
        .groupby("product", sort=True)[["total_sales", "quantity"]]
        .sum()
    )
    top_by_revenue = sorted(
        ((str(product), round(float(row["total_sales"]), 2))
         for product, row in totals.iterrows()),
        key=lambda item: (-item[1], item[0]),
    )[0]
    top_by_units = sorted(
        ((str(product), int(row["quantity"])) for product, row in totals.iterrows()),
        key=lambda item: (-item[1], item[0]),
    )[0]

    # Keep every co-leader at the top unit count. The older single-leader
    # field stays for compatibility with existing reports and charts.
    unit_coleaders = [
        {"product": product, "units_sold": units}
        for product, units in sorted(
            ((str(product), int(row["quantity"]))
             for product, row in totals.iterrows()),
            key=lambda item: (-item[1], item[0]),
        )
        if units == top_by_units[1]
    ]
    return {
        "month_count": month_count,
        "first_month": first["month"],
        "last_month": last["month"],
        "overall_revenue_change": overall_change,
        "highest_revenue_month": highest_month,
        "lowest_revenue_month": lowest_month,
        "largest_monthly_revenue_increase": largest_increase,
        "largest_monthly_revenue_decrease": largest_decrease,
        "largest_monthly_revenue_percentage_increase": largest_percentage_increase,
        "largest_monthly_revenue_percentage_decrease": largest_percentage_decrease,
        "top_product_by_revenue_full_period": {
            "product": top_by_revenue[0], "revenue": top_by_revenue[1]
        },
        "top_product_by_units_full_period": {
            "product": top_by_units[0], "units_sold": top_by_units[1]
        },
        "top_products_tied_by_units_full_period": unit_coleaders,
    }
