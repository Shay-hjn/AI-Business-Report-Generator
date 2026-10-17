from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.analytics.pipeline import analyze_csv_bytes


router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("")
async def create_report(file: UploadFile = File(...)):
    """Upload a CSV and return its calculated business analysis."""

    try:
        # Accept CSV files only
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=422,
                detail="Please upload a CSV file (.csv).",
            )

        # Read the uploaded file
        csv_content = await file.read()

        # Validate the CSV and calculate business metrics
        result = analyze_csv_bytes(csv_content)

        return result

    except ValueError as error:
        # Convert CSV validation errors into HTTP responses
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    finally:
        await file.close()
