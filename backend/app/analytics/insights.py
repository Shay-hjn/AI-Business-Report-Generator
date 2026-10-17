# Thresholds for notable change detection
OVERALL_REVENUE_THRESHOLD = 20
SEGMENT_REVENUE_THRESHOLD = 30
PRODUCT_SPIKE_THRESHOLD = 100
REVENUE_IMPACT_THRESHOLD = 0.10
VOLUME_DIVERGENCE_THRESHOLD = 10

# Limit the number of findings for each dimension
MAX_SEGMENT_FINDINGS = 2
MAX_PRODUCT_FINDINGS = 1


def percentage_change(previous: float, current: float) -> float | None:
    """Calculate percentage change, avoiding division by zero."""

    if previous == 0:
        return None

    return round((current - previous) / previous * 100, 2)


def detect_segment_changes(
    previous_groups: dict,
    current_groups: dict,
    dimension: str,
    minimum_impact: float,
) -> list[dict]:
    """Detect significant category, region, or product revenue changes."""

    findings = []

    all_names = set(previous_groups) | set(current_groups)

    for name in all_names:
        previous = previous_groups.get(name, 0)
        current = current_groups.get(name, 0)

        absolute_change = round(current - previous, 2)

        # Ignore changes with insufficient financial impact
        if absolute_change == 0 or abs(absolute_change) < minimum_impact:
            continue

        change_pct = percentage_change(previous, current)

        # Handle segments that previously generated no revenue
        if previous == 0:
            if current <= 0:
                continue

            finding_type = f"new_{dimension}_revenue"

        elif dimension == "product":
            # Only detect major product revenue increases
            if change_pct < PRODUCT_SPIKE_THRESHOLD:
                continue

            finding_type = "product_revenue_spike"

        else:
            # Detect significant category and regional changes
            if abs(change_pct) < SEGMENT_REVENUE_THRESHOLD:
                continue

            finding_type = f"{dimension}_revenue_change"

        findings.append(
            {
                "type": finding_type,
                "name": name,
                "previous_revenue": round(previous, 2),
                "current_revenue": round(current, 2),
                "absolute_change": absolute_change,
                "percentage_change": change_pct,
            }
        )

    # Prioritize findings with the largest absolute revenue impact
    findings.sort(
        key=lambda item: (
            -abs(item["absolute_change"]),
            item["name"],
        )
    )

    limit = MAX_PRODUCT_FINDINGS if dimension == "product" else MAX_SEGMENT_FINDINGS

    return findings[:limit]


def detect_notable_changes(
    monthly_kpis: list[dict],
    comparisons: list[dict],
    breakdowns: dict,
) -> list[dict]:
    """Detect notable business changes using deterministic rules."""

    findings = []

    kpis_by_month = {item["month"]: item for item in monthly_kpis}

    for comparison in comparisons:
        from_month = comparison["from_month"]
        to_month = comparison["to_month"]

        previous_kpis = kpis_by_month[from_month]
        current_kpis = kpis_by_month[to_month]

        previous_revenue = previous_kpis["total_revenue"]
        current_revenue = current_kpis["total_revenue"]

        revenue_change = comparison["changes"]["total_revenue"]
        revenue_change_pct = revenue_change["percentage_change"]

        # Rule 1: Significant overall revenue changes
        if (
            revenue_change_pct is not None
            and abs(revenue_change_pct) >= OVERALL_REVENUE_THRESHOLD
        ):
            findings.append(
                {
                    "type": "overall_revenue_change",
                    "from_month": from_month,
                    "to_month": to_month,
                    "previous_revenue": previous_revenue,
                    "current_revenue": current_revenue,
                    "absolute_change": revenue_change["absolute_change"],
                    "percentage_change": revenue_change_pct,
                }
            )

        elif previous_revenue == 0 and current_revenue > 0:
            findings.append(
                {
                    "type": "revenue_started",
                    "from_month": from_month,
                    "to_month": to_month,
                    "previous_revenue": previous_revenue,
                    "current_revenue": current_revenue,
                    "absolute_change": revenue_change["absolute_change"],
                    "percentage_change": None,
                }
            )

        # Minimum impact: 10% of previous month's total revenue
        minimum_impact = previous_revenue * REVENUE_IMPACT_THRESHOLD

        previous_breakdown = breakdowns.get(from_month, {})
        current_breakdown = breakdowns.get(to_month, {})

        # Rules 2, 3, 4: Category, region, and product changes
        for dimension in ["category", "region", "product"]:
            segment_findings = detect_segment_changes(
                previous_groups=previous_breakdown.get(dimension, {}),
                current_groups=current_breakdown.get(dimension, {}),
                dimension=dimension,
                minimum_impact=minimum_impact,
            )

            for finding in segment_findings:
                findings.append(
                    {
                        "from_month": from_month,
                        "to_month": to_month,
                        **finding,
                    }
                )

        # Rule 5: Revenue-volume divergence
        order_change_pct = comparison["changes"]["order_count"]["percentage_change"]

        units_change_pct = comparison["changes"]["units_sold"]["percentage_change"]

        revenue_declined = (
            revenue_change_pct is not None
            and revenue_change_pct <= -VOLUME_DIVERGENCE_THRESHOLD
        )

        orders_increased = (
            order_change_pct is not None
            and order_change_pct >= VOLUME_DIVERGENCE_THRESHOLD
        )

        units_increased = (
            units_change_pct is not None
            and units_change_pct >= VOLUME_DIVERGENCE_THRESHOLD
        )

        if revenue_declined and (orders_increased or units_increased):
            findings.append(
                {
                    "type": "revenue_volume_divergence",
                    "from_month": from_month,
                    "to_month": to_month,
                    "revenue_change_pct": revenue_change_pct,
                    "order_count_change_pct": order_change_pct,
                    "units_sold_change_pct": units_change_pct,
                }
            )

    return findings
