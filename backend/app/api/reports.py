from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.app.analytics.pipeline import analyze_csv_bytes
from backend.app.services.llm_service import generate_business_report


router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("")
async def create_report(file: UploadFile = File(...)):
    """
    Upload a CSV, calculate business metrics, and generate
    an AI business report.
    """

    try:
        # Step 1: Accept CSV files only.
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=422,
                detail="Please upload a CSV file (.csv).",
            )

        # Step 2: Read the uploaded CSV.
        csv_content = await file.read()

        # Step 3: Validate and analyze the data with Python.
        # Invalid data raises ValueError before any LLM call.
        analysis = await run_in_threadpool(
            analyze_csv_bytes,
            csv_content,
        )

        # Step 4: Generate the AI narrative from verified results.
        # The LLM service handles failures and returns a fallback.
        ai_result = await run_in_threadpool(
            generate_business_report,
            analysis,
        )

        # Step 5: Combine Python analytics and AI results.
        return {
            **analysis,
            **ai_result,
        }

    except ValueError as error:
        # CSV validation errors become HTTP 422 responses.
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    finally:
        # Always close the uploaded file.
        await file.close()
