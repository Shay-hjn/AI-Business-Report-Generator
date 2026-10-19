import argparse
import json
from pathlib import Path

from backend.app.analytics.pipeline import analyze_csv_bytes
from backend.app.services.llm_service import (
    build_segment_directions,
    generate_business_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"


def main():
    parser = argparse.ArgumentParser(
        description="Test AI report generation with a sample CSV."
    )

    parser.add_argument(
        "filename",
        nargs="?",
        default="sales_02_category_crash.csv",
        help="CSV filename inside data/samples/",
    )

    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="Show Python results without calling Gemini.",
    )

    args = parser.parse_args()

    csv_path = SAMPLES_DIR / args.filename

    if not csv_path.is_file():
        parser.error(f"CSV file not found: {csv_path}")

    # Analyze the CSV using Python.
    analysis = analyze_csv_bytes(csv_path.read_bytes())

    print("\n=== DATASET ===")
    print(csv_path.name)

    print("\n=== PYTHON-CALCULATED REVENUE ===")
    for month in analysis["monthly_kpis"]:
        print(f"{month['month']}: {month['total_revenue']:.2f}")

    # Verify category and regional directions independently.
    directions = build_segment_directions(analysis)

    print("\n=== PYTHON-VERIFIED SEGMENT DIRECTIONS ===")
    print(json.dumps(directions, indent=2))

    if args.analysis_only:
        return

    # Generate the real AI report.
    result = generate_business_report(analysis)

    print("\n=== AI GENERATION STATUS ===")
    print("Narrative generated:", result["narrative_generated"])

    if result["narrative_generated"]:
        print("\n=== AI BUSINESS REPORT ===")
        print(
            json.dumps(
                result["ai_report"],
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print("\nAI narrative unavailable. Python calculations remain available.")


if __name__ == "__main__":
    main()
