from pydantic import BaseModel, ConfigDict


class BusinessReport(BaseModel):
    """Structure of the AI-generated business report."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    key_insights: list[str]
    notable_changes: list[str]
    recommendations: list[str]
