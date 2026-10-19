# Sales Intelligence — AI Business Report Generator

Sales Intelligence transforms a sales CSV into a structured business performance report. It combines **Python-calculated metrics** with a **Google Gemini-generated narrative**, interactive visualizations, and a downloadable PDF.

The application is designed around a clear division of responsibilities: Python validates the data and computes the numbers; Gemini turns those verified results into a concise, readable management summary. The original CSV is not sent to the language model.

## Features

- **CSV validation:** checks required columns, valid dates, numeric values, discounts, and consistency between line-item revenue and its underlying price, quantity, and discount.
- **Business metrics:** monthly revenue, distinct order count, units sold, average order value, and revenue per unit.
- **Performance comparisons:** changes between reported periods, revenue breakdowns by category, region, and product, and notable movements and rankings.
- **AI-assisted reporting:** an executive summary, key insights, and notable changes generated from Python-derived evidence rather than raw transactions.
- **Grounding safeguards:** structured-output validation and checks for several kinds of unsupported numerical, ranking, currency, and causal claims.
- **Interactive dashboard:** a Streamlit interface with KPI cards and Altair charts.
- **PDF export:** a formatted ReportLab report built from the existing analysis and narrative, without making another AI request.
- **Graceful degradation:** if Gemini is unavailable or its response fails validation, the verified analytics and charts remain available.

## How it works

```text
Sales CSV
   │
   ▼
Streamlit dashboard  (frontend/app.py)
   │  POST /reports — CSV upload
   ▼
FastAPI              (backend/app/api/reports.py)
   │
   ├── Validate CSV data
   ├── Calculate KPIs, comparisons, rankings, and notable changes
   └── Send structured analytical evidence to Gemini
                                  │
                                  ▼
                         Generate narrative
                                  │
                                  ▼
                         Validate AI response
   │
   ▼
JSON report: verified metrics + optional narrative
   │
   ├── Streamlit dashboard and charts
   └── Downloadable PDF
```

The backend uses **FastAPI**, **Pandas**, and **Pydantic**. The frontend uses **Streamlit** and **Altair**; **ReportLab** creates the PDF. No database or report-history service is required for the current workflow.

## Getting started

### Prerequisites

- Python **3.14** (the development/test environment; other versions have not been fully verified).
- A [Google Gemini API key](https://aistudio.google.com/apikey) to generate AI narratives.
- Internet access for Gemini requests. CSV analytics can still run when the AI service is unavailable.

### 1. Install dependencies

Clone the repository and open a terminal in its root directory.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure Gemini

Open the newly created `.env` file and provide your API key:

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.8-flash
GEMINI_API_KEY=your_gemini_api_key
LLM_RETRY_CONTENT_VALIDATION=0
```

`LLM_MODEL` is configurable: use a Gemini model that is available to your API key. **Model switching is manual**—change the value and restart the FastAPI server. The application does not automatically switch models when an API request fails.

Optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_THINKING_LEVEL` | `medium` | Gemini thinking level: `low`, `medium`, or `high` |
| `LLM_MAX_OUTPUT_TOKENS` | `6000` | Maximum generated tokens (256–65,536) |
| `LLM_RETRY_CONTENT_VALIDATION` | `0` | Set to `1` to allow one additional attempt when returned narrative content fails validation; does not retry HTTP/API errors |

Keep `.env` private. The repository includes `.env.example` only as a configuration template.

### 3. Run the application

Start the FastAPI backend in one terminal:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Start Streamlit in a **second** terminal, using the same virtual environment:

```powershell
python -m streamlit run frontend/app.py
```

Open **http://localhost:8501**. Upload a sales CSV, select **Generate Report**, explore the results, and optionally download a PDF.

The API is available at **http://127.0.0.1:8000**; interactive API documentation is at **http://127.0.0.1:8000/docs**.

## CSV format

Select **View CSV input template** in the dashboard to inspect the required columns and download an empty template. The required header is:

```csv
order_id,date,customer_id,product,category,region,quantity,unit_price,discount_pct,total_sales
```

| Field | Requirement |
| --- | --- |
| `order_id`, `customer_id`, `product`, `category`, `region` | Non-empty text |
| `date` | Valid date in `YYYY-MM-DD` format |
| `quantity` | Positive whole number |
| `unit_price` | Non-negative number |
| `discount_pct` | Percentage from 0 to 100 |
| `total_sales` | Non-negative number consistent with the calculated line-item revenue |

Each row represents a sales **line item**. Multiple rows can share an `order_id`; order count is based on distinct order IDs within each reported month.

The application checks that:

```text
total_sales = quantity × unit_price × (1 − discount_pct / 100)
```

A rounding tolerance of approximately **0.01** is allowed. All monetary amounts are interpreted as **EUR**.

The [`data/samples/`](data/samples/) directory contains synthetic datasets with different business patterns, including growth, declines, sparse reporting months, ranking ties, and zero-revenue periods. `sales_07_corrupted_missing_column.csv` is intentionally invalid for testing CSV validation.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check; returns `{"status":"ok"}` |
| `POST` | `/reports` | Accepts a multipart `.csv` upload in the `file` field and returns the structured report as JSON |
| `GET` | `/docs` | FastAPI's interactive OpenAPI documentation |

Example request, with the backend running:

```bash
curl -X POST http://127.0.0.1:8000/reports \
  -F "file=@data/samples/sales_01_steady_growth.csv"
```

Invalid CSV input produces **HTTP 422**, without requesting an AI narrative. If Gemini fails after a valid analysis, the API returns the calculated metrics with `narrative_generated: false` and `ai_report: null`; the dashboard indicates that the AI narrative is unavailable.

## Testing

Run the offline regression suite:

```bash
python -m pytest tests/ -q
```

Tests cover CSV validation, financial calculations, period and segment comparisons, API responses, narrative safeguards, PDF generation, and selected frontend behavior. Model responses are mocked, so the offline suite does **not** require paid API calls.

For a local analysis check without contacting Gemini:

```bash
python -m scripts.check_real_report sales_09_eight_month_business_performance.csv --analysis-only
```

To perform a live Gemini connectivity check (requires an API key and consumes API quota):

```bash
python -m scripts.check_llm
```

## Design choices

| Choice | Reason |
| --- | --- |
| Deterministic financial calculations in Python | Keeps metrics reproducible and independent of LLM arithmetic |
| Send analytical evidence, not raw CSV rows, to Gemini | Limits the data shared and narrows the model's task to interpretation and writing |
| Validate the AI's structured output and factual claims | Detects several known failure patterns before displaying the narrative |
| Separate API, analytics, and UI responsibilities | Makes the code easier to test, review, and extend |
| Keep analytics available when Gemini fails | Ensures an API outage does not discard useful computed results |
| Generate PDF from the report already in memory | Avoids duplicate calculations and extra LLM requests |

## Assumptions and limitations

- **EUR only:** no currency conversion or multi-currency aggregation.
- **Reported months only:** missing calendar months are not assumed to have zero sales. Comparisons use successive months present in the CSV, which may not be consecutive calendar months.
- **Zero baselines:** percentage changes with a zero denominator are undefined rather than represented as an invented percentage.
- **Descriptive analytics:** revenue trends do not establish profit, customer demand, or the causes of a change. The application does not infer unverified business causes.
- **LLM accuracy:** validation mitigates several hallucination risks but cannot guarantee that every narrative statement is correct. Important business decisions require human review.
- **API limitations:** Gemini availability, quotas, model access, and response times vary. No automatic model fallback or HTTP retry mechanism is implemented.
- **Local-first operation:** the Streamlit frontend expects FastAPI at `127.0.0.1:8000`. Deployment to separate hosts would require configuring the API URL.
- **No persistence or account system:** uploaded reports are processed on demand; the application does not provide authentication, scheduled generation, or a saved report history.

## Repository structure

```text
backend/
  app/
    analytics/           CSV validation, metrics, insights, and pipeline
    api/                 FastAPI report endpoint
    services/            Gemini integration and narrative validation
    main.py              FastAPI application and health endpoint
frontend/
  app.py                 Streamlit dashboard
  styles.css             Dashboard styling
  pdf_export.py          ReportLab PDF exporter
data/samples/             Synthetic CSV datasets
scripts/                  Optional local diagnostic commands
tests/                    Offline regression tests
.streamlit/config.toml    Streamlit theme configuration
.env.example             Environment variable template
requirements.txt         Python dependencies
README.md
```

## Security and data handling

The application processes CSV uploads locally through its FastAPI backend. The **Gemini request uses derived analytical data**, not an attachment containing the original CSV. Avoid uploading confidential or sensitive information to external AI services unless you have assessed the applicable data-handling requirements.

Never commit `.env`, API keys, virtual environments, or confidential sales files. The repository's sample data is synthetic, and `.gitignore` excludes common local artifacts.

## Development note

AI-assisted development tools, including ChatGPT, were used during implementation, debugging, test-case design, and documentation. The application itself uses Google Gemini for report narration; core financial calculations and validation remain in Python.
