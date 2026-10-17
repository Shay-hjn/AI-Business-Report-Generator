from pathlib import Path

import pytest

from backend.app.analytics.pipeline import analyze_csv_bytes


SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def analyze_sample(filename: str) -> dict:
    """Load and analyze one synthetic CSV dataset."""

    csv_content = (SAMPLES_DIR / filename).read_bytes()

    return analyze_csv_bytes(csv_content)


@pytest.mark.parametrize(
    "filename, expected_revenues",
    [
        (
            "sales_01_steady_growth.csv",
            {
                "2026-08": 85660.65,
                "2026-09": 123126.20,
            },
        ),
        (
            "sales_02_category_crash.csv",
            {
                "2026-08": 140954.75,
                "2026-09": 64723.90,
            },
        ),
        (
            "sales_03_viral_product_boom.csv",
            {
                "2026-08": 75536.85,
                "2026-09": 127328.85,
            },
        ),
        (
            "sales_04_regional_shift.csv",
            {
                "2026-08": 106309.60,
                "2026-09": 106309.60,
            },
        ),
        (
            "sales_05_high_volume_low_revenue.csv",
            {
                "2026-08": 84380.00,
                "2026-09": 57920.70,
            },
        ),
        (
            "sales_06_q3_seasonal_peak.csv",
            {
                "2026-07": 55411.40,
                "2026-08": 118479.00,
                "2026-09": 63108.05,
            },
        ),
    ],
)
def test_expected_monthly_revenues(filename, expected_revenues):
    """Verify the revenue totals for all six valid datasets."""

    result = analyze_sample(filename)

    actual_revenues = {
        item["month"]: item["total_revenue"] for item in result["monthly_kpis"]
    }

    assert actual_revenues == expected_revenues

    # Category breakdowns must match total monthly revenue
    for month, expected_revenue in expected_revenues.items():
        category_revenue = sum(result["revenue_breakdowns"][month]["category"].values())

        assert round(category_revenue, 2) == expected_revenue


def test_steady_growth():
    result = analyze_sample("sales_01_steady_growth.csv")

    growth = result["monthly_kpis"][1]["revenue_growth_pct"]

    assert growth == 43.74

    assert any(
        finding["type"] == "overall_revenue_change"
        for finding in result["notable_changes"]
    )


def test_category_crash():
    result = analyze_sample("sales_02_category_crash.csv")

    assert any(
        finding["type"] == "category_revenue_change"
        and finding["name"] == "Electronics"
        and finding["percentage_change"] < -80
        for finding in result["notable_changes"]
    )


def test_viral_product_boom():
    result = analyze_sample("sales_03_viral_product_boom.csv")

    assert result["top_revenue_product"]["product"] == "AI Smart Webcam 4K"

    assert any(
        finding["type"] == "product_revenue_spike"
        and finding["name"] == "AI Smart Webcam 4K"
        for finding in result["notable_changes"]
    )


def test_regional_shift():
    result = analyze_sample("sales_04_regional_shift.csv")

    august, september = result["monthly_kpis"]

    # Overall revenue remains unchanged
    assert august["total_revenue"] == september["total_revenue"]

    findings = result["notable_changes"]

    # There should be no overall revenue-change finding
    assert not any(finding["type"] == "overall_revenue_change" for finding in findings)

    # But important regional movements must be detected
    assert any(
        finding["type"] == "region_revenue_change"
        and finding["name"] == "North"
        and finding["percentage_change"] < -80
        for finding in findings
    )

    assert any(
        finding["type"] == "region_revenue_change"
        and finding["name"] == "South"
        and finding["percentage_change"] > 80
        for finding in findings
    )


def test_high_volume_low_revenue():
    result = analyze_sample("sales_05_high_volume_low_revenue.csv")

    august, september = result["monthly_kpis"]

    assert september["order_count"] > august["order_count"]
    assert september["units_sold"] > august["units_sold"]
    assert september["total_revenue"] < august["total_revenue"]

    assert any(
        finding["type"] == "revenue_volume_divergence"
        for finding in result["notable_changes"]
    )


def test_three_month_seasonal_peak():
    result = analyze_sample("sales_06_q3_seasonal_peak.csv")

    assert len(result["monthly_kpis"]) == 3
    assert len(result["comparisons"]) == 2

    # July to August
    first_change = result["comparisons"][0]["changes"]["total_revenue"]

    assert first_change["percentage_change"] == 113.82

    # August to September
    second_change = result["comparisons"][1]["changes"]["total_revenue"]

    assert second_change["percentage_change"] == -46.73


def test_corrupted_dataset_rejected():
    with pytest.raises(
        ValueError,
        match="Missing required columns: total_sales",
    ):
        analyze_sample("sales_07_corrupted_missing_column.csv")


def test_empty_csv_rejected():
    with pytest.raises(
        ValueError,
        match="The uploaded CSV file is empty",
    ):
        analyze_csv_bytes(b"")


def test_malformed_csv_rejected():
    malformed_content = b'order_id,date\n"unfinished,2026-08-01\n'

    with pytest.raises(
        ValueError,
        match="Could not read the CSV file",
    ):
        analyze_csv_bytes(malformed_content)


def test_invalid_encoding_rejected():
    with pytest.raises(
        ValueError,
        match="Could not read the CSV file",
    ):
        analyze_csv_bytes(b"\xff\xfe\xff")
