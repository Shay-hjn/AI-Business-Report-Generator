from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_health_endpoint():
    """Check that the backend responds successfully."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_csv_upload():
    """A valid CSV should return calculated business results."""

    filename = "sales_01_steady_growth.csv"
    csv_content = (SAMPLES_DIR / filename).read_bytes()

    response = client.post(
        "/reports",
        files={"file": (filename, csv_content, "text/csv")},
    )

    assert response.status_code == 200

    result = response.json()

    assert len(result["monthly_kpis"]) == 2
    assert result["monthly_kpis"][0]["total_revenue"] == 85660.65
    assert result["monthly_kpis"][1]["total_revenue"] == 123126.20

    assert len(result["comparisons"]) == 1
    assert "revenue_breakdowns" in result
    assert "top_revenue_product" in result
    assert "notable_changes" in result


def test_invalid_csv_upload():
    """An invalid CSV should return HTTP 422."""

    filename = "sales_07_corrupted_missing_column.csv"
    csv_content = (SAMPLES_DIR / filename).read_bytes()

    response = client.post(
        "/reports",
        files={"file": (filename, csv_content, "text/csv")},
    )

    assert response.status_code == 422
    assert "Missing required columns: total_sales" in (response.json()["detail"])


def test_empty_csv_upload():
    """An empty CSV should be rejected gracefully."""

    response = client.post(
        "/reports",
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_non_csv_upload():
    """Files without a CSV extension should be rejected."""

    response = client.post(
        "/reports",
        files={"file": ("document.txt", b"some text", "text/plain")},
    )

    assert response.status_code == 422
    assert "Please upload a CSV file" in (response.json()["detail"])
