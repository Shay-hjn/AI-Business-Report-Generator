# Sales Intelligence — AI Business Report Generator

Sales Intelligence converts sales CSV files into business performance reports with **validated financial metrics**, **AI-generated management summaries**, **interactive charts**, and **downloadable PDFs**.

The application separates numerical analysis from natural-language generation. Python validates the uploaded data and calculates the metrics; Google Gemini uses those calculated results to write an executive summary, key insights, and notable changes. The original CSV is not uploaded to Gemini.

## Features

- **CSV validation:** Checks required columns, date formats, numerical values, discounts, and line-item revenue consistency.
- **Business analytics:** Calculates monthly revenue, distinct orders, units sold, average order value, and revenue per unit.
- **Period comparisons:** Tracks changes across reported months, including category and regional performance, product rankings, and notable movements.
- **AI management report:** Uses Gemini to produce a structured executive summary, key insights, and notable changes from Python-derived analytical data.
- **Response validation:** Validates the generated JSON against a defined Pydantic schema.
- **Interactive dashboard:** Presents KPIs and revenue trends using Streamlit and Altair.
- **PDF export:** Produces a formatted report using ReportLab from the existing results, without another Gemini request.
- **Graceful error handling:** Keeps computed KPIs and charts available when the AI narrative cannot be generated.

## Architecture

```text
Sales CSV
   |
   v
Streamlit dashboard (frontend/app.py)
   |  POST /reports — multipart CSV upload
   v
FastAPI backend (backend/app/api/reports.py)
   |
   +-- CSV validation
   +-- Python analytics: KPIs, comparisons, rankings, notable changes
   +-- Gemini: narrative generation from structured analytical data
   |      |
   |      +-- JSON parsing and Pydantic schema validation
   |
   v
Structured API response: analytics + optional AI narrative
   |
   +-- Streamlit dashboard and Altair charts
   +-- Downloadable ReportLab PDF
```

**Technology stack:** Python, FastAPI, Pandas, Pydantic, Google Gemini API, Streamlit, Altair, and ReportLab.

The application processes reports on demand and does not require a database.

## Getting started

### Prerequisites

- **Python 3.14**, used for development and testing. Other versions have not been fully verified.
- A [Google Gemini API key](https://aistudio.google.com/apikey) for AI narrative generation.
- Internet access for Gemini requests.

### 1. Clone and install

```bash
git clone https://github.com/Shay-hjn/AI-Business-Report-Generator.git
cd AI-Business-Report-Generator
```

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

Edit the local `.env` file and add your API key:

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.8-flash
GEMINI_API_KEY=your_gemini_api_key
LLM_RETRY_CONTENT_VALIDATION=0
```

`LLM_MODEL` selects the Gemini model used for generation. To switch models, update the setting and restart FastAPI. The selected model must be accessible to your API key; availability and quotas vary.

Additional configuration:

| Setting | Default | Description |
| --- | --- | --- |
| `LLM_THINKING_LEVEL` | `medium` | Gemini thinking level: `low`, `medium`, or `high` |
| `LLM_MAX_OUTPUT_TOKENS` | `6000` | Output token limit (256–65,536) |
| `LLM_RETRY_CONTENT_VALIDATION` | `0` | Set to `1` to allow one additional generation attempt when JSON parsing or schema validation fails |

Keep `.env` private. `.env.example` contains placeholder values for local setup.

### 3. Run the application

Start **FastAPI** in one terminal:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Start **Streamlit** in another terminal, with the same virtual environment activated:

```powershell
python -m streamlit run frontend/app.py
```

Open **http://localhost:8501** to upload a CSV, generate a report, view the analytics, and download the PDF.

The backend runs at **http://127.0.0.1:8000**, with interactive API documentation at **http://127.0.0.1:8000/docs**.

## CSV input format

The dashboard's **View CSV input template** dialog displays the required columns and provides a blank CSV download.

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
| `total_sales` | Non-negative number matching calculated line-item revenue |

Each CSV row represents a sales line item. Multiple rows can share an `order_id`; monthly order counts use distinct order IDs.

The expected revenue for each row is:

```text
total_sales = quantity * unit_price * (1 - discount_pct / 100)
```

Validation allows a difference of up to approximately **€0.01** for rounding. All monetary figures are interpreted as **EUR**.

The [`data/samples/`](data/samples/) directory provides synthetic datasets covering growth, contractions, unusual volume/revenue relationships, missing reporting months, zero revenue, and ranking ties. `sales_07_corrupted_missing_column.csv` is intentionally invalid and can be used to test CSV validation errors.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check returning `{"status":"ok"}` |
| `POST` | `/reports` | Accepts a multipart CSV upload in the `file` field and returns the report as JSON |
| `GET` | `/docs` | Interactive OpenAPI documentation |

Example request with FastAPI running:

```bash
curl -X POST http://127.0.0.1:8000/reports \
  -F "file=@data/samples/sales_01_steady_growth.csv"
```

Invalid CSV input produces **HTTP 422**. When the CSV is valid but Gemini is unavailable or returns an invalid structured response, the API still returns the computed analytics, with `narrative_generated: false` and `ai_report: null`.

## Testing

Run the offline regression suite:

```bash
python -m pytest tests/ -q
```

Tests cover CSV validation, KPI calculations, period and segment comparisons, API responses, Gemini response formatting, PDF generation, and selected frontend behavior. Model responses are mocked, so the suite does not make live Gemini API calls.

To inspect Python-generated analytics without contacting Gemini:

```bash
python -m scripts.check_real_report sales_09_eight_month_business_performance.csv --analysis-only
```

To check the live configured Gemini connection (requires an API key and uses API quota):

```bash
python -m scripts.check_llm
```

## Design decisions

| Decision | Rationale |
| --- | --- |
| Calculate financial metrics in Python | Provides reproducible numerical results independent of the language model |
| Send aggregated analytical data to Gemini | Focuses the model on report writing while reducing exposure of individual transactions |
| Validate structured AI responses with Pydantic | Enforces a consistent report format for the dashboard and PDF exporter |
| Separate the API, analytics, and presentation layers | Improves testability and maintainability |
| Keep analytics available if AI generation fails | Preserves useful results during model or API errors |
| Generate PDFs from the existing API response | Avoids duplicate analysis and additional AI calls |

## Assumptions and limitations

- **Currency:** Monetary values are interpreted as EUR; multi-currency aggregation and conversion are not supported.
- **Reporting gaps:** Missing calendar months are not treated as zero-sales months. Comparisons use successive *reported* months, which may not be consecutive on the calendar.
- **Zero baselines:** Percentage changes with a zero denominator are reported as undefined rather than as a numerical percentage.
- **Interpretation:** Revenue data alone does not establish profitability, customer demand, or the causes of performance changes. AI-generated narratives may contain inaccuracies and should be reviewed before business decisions.
- **Model availability:** Gemini model access, rate limits, and latency depend on the API service and account. Model selection is manual; requests are not automatically routed to other models.
- **Local configuration:** The Streamlit frontend expects FastAPI at `127.0.0.1:8000`. Hosting the services separately requires configuring the API URL.
- **Scope:** Reports are processed on demand. User accounts, saved report history, and scheduled report generation are not included.

## Project structure

```text
backend/
  app/
    analytics/          CSV validation, KPIs, insights, pipeline
    api/                FastAPI reports endpoint
    services/           Gemini integration and response validation
    main.py             FastAPI application and health endpoint
frontend/
  app.py                Streamlit dashboard
  styles.css            Dashboard styles
  pdf_export.py         PDF exporter
data/samples/            Synthetic CSV test datasets
scripts/                 Local diagnostic commands
tests/                   Offline regression tests
.streamlit/config.toml   Streamlit configuration
.env.example             Environment variable template
requirements.txt         Python dependencies
README.md
```

## Security and data handling

Sales CSV files are processed by the local FastAPI service. Gemini receives selected analytical data derived from the CSV, rather than the uploaded file itself. Review your data-handling requirements before processing confidential or personal business information with an external AI service.

Do not commit API keys, `.env`, `.venv`, generated caches, or confidential CSV files to the repository. The included sample datasets are synthetic.

## AI-assisted development

AI coding tools, including ChatGPT, were used to assist with implementation, debugging, test design, and documentation. The application uses Google Gemini to generate management narratives; CSV validation and financial calculations are implemented in Python.
