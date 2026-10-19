"""Check that single-month reports receive appropriate prompt instructions."""

from backend.app.services.llm_service import SYSTEM_PROMPT


def test_single_month_prompt_excludes_unverified_pricing_mix():
    assert "For single-month reports" in SYSTEM_PROMPT
    assert "pricing mix" in SYSTEM_PROMPT
