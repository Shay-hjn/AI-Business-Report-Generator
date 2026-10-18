from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


# Simulated successful AI response.
FAKE_AI_RESULT = {
    "narrative_generated": True,
    "ai_report": {
        "executive_summary": ("Revenue increased between August and September."),
        "key_insights": ["September revenue was higher than August revenue."],
        "notable_changes": ["Overall revenue increased."],
    },
}


def upload_sample(filename):
    """Upload a sample CSV to the reports endpoint."""

    csv_content = (SAMPLES_DIR / filename).read_bytes()

    return client.post(
        "/reports",
        files={
            "file": (
                filename,
                csv_content,
                "text/csv",
            )
        },
    )


def test_health_endpoint():
    """Check that the backend responds successfully."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("backend.app.api.reports.generate_business_report")
def test_valid_csv_upload(mock_generate_report):
    """Valid CSV should return analytics and the AI report."""

    # Simulate a successful Groq response.
    mock_generate_report.return_value = FAKE_AI_RESULT

    response = upload_sample("sales_01_steady_growth.csv")

    assert response.status_code == 200

    result = response.json()

    # Verify the real Python analytics.
    assert len(result["monthly_kpis"]) == 2

    assert result["monthly_kpis"][0]["total_revenue"] == 85660.65

    assert result["monthly_kpis"][1]["total_revenue"] == 123126.20

    assert len(result["comparisons"]) == 1
    assert "revenue_breakdowns" in result
    assert "top_revenue_product" in result
    assert "notable_changes" in result

    # Verify the simulated AI report was included.
    assert result["narrative_generated"] is True
    assert result["ai_report"] == FAKE_AI_RESULT["ai_report"]
    assert set(result["ai_report"]) == {
        "executive_summary", "key_insights", "notable_changes"
    }

    # Verify that the LLM service was called exactly once.
    mock_generate_report.assert_called_once()

    # Verify the LLM received verified analytical results.
    analysis_sent_to_llm = mock_generate_report.call_args.args[0]

    assert analysis_sent_to_llm["monthly_kpis"][1]["total_revenue"] == 123126.20

    assert "revenue_breakdowns" in analysis_sent_to_llm


@patch("backend.app.api.reports.generate_business_report")
def test_invalid_csv_upload(mock_generate_report):
    """Invalid CSV should return HTTP 422 without calling Groq."""

    response = upload_sample("sales_07_corrupted_missing_column.csv")

    assert response.status_code == 422

    assert "Missing required columns: total_sales" in (response.json()["detail"])

    # Critical: invalid input must not reach the LLM.
    mock_generate_report.assert_not_called()


@patch("backend.app.api.reports.generate_business_report")
def test_empty_csv_upload(mock_generate_report):
    """Empty CSV should return HTTP 422 without calling Groq."""

    response = client.post(
        "/reports",
        files={
            "file": (
                "empty.csv",
                b"",
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()

    mock_generate_report.assert_not_called()


@patch("backend.app.api.reports.generate_business_report")
def test_non_csv_upload(mock_generate_report):
    """Non-CSV uploads should be rejected before LLM generation."""

    response = client.post(
        "/reports",
        files={
            "file": (
                "document.txt",
                b"some text",
                "text/plain",
            )
        },
    )

    assert response.status_code == 422

    assert "Please upload a CSV file" in (response.json()["detail"])

    mock_generate_report.assert_not_called()


@patch("backend.app.api.reports.generate_business_report")
def test_groq_failure_preserves_analytics(mock_generate_report):
    """
    If AI generation is unavailable, valid CSV analytics
    must still be returned with HTTP 200.
    """

    # Simulate the LLM service's graceful fallback.
    mock_generate_report.return_value = {
        "narrative_generated": False,
        "ai_report": None,
    }

    response = upload_sample("sales_05_high_volume_low_revenue.csv")

    # The CSV is valid, even though the AI is unavailable.
    assert response.status_code == 200

    result = response.json()

    # Python-calculated metrics must remain available.
    assert result["monthly_kpis"][0]["total_revenue"] == 84380.00
    assert result["monthly_kpis"][1]["total_revenue"] == 57920.70

    assert "comparisons" in result
    assert "revenue_breakdowns" in result
    assert "top_revenue_product" in result
    assert "notable_changes" in result

    # Only the AI narrative is unavailable.
    assert result["narrative_generated"] is False
    assert result["ai_report"] is None

    mock_generate_report.assert_called_once()
