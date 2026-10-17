from fastapi import FastAPI

from backend.app.api.reports import router as reports_router


app = FastAPI(
    title="AI Business Report Generator",
    version="0.1.0",
)


# Register the report endpoints
app.include_router(reports_router)


@app.get("/health")
def health_check():
    """Check whether the API is running."""
    return {"status": "ok"}
