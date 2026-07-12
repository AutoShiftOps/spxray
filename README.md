# 🔍 SP Migration Companion

**AI-powered stored procedure analyzer for database migration planning**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python)](https://python.org)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Mistral--7B-FFD21E?style=flat-square&logo=huggingface)](https://huggingface.co)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square&logo=render)](https://render.com)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

[Live Demo](#) · [API Docs](#api-reference) · [Report Issue](issues)

---

</div>

## What it does

Business Solution Architects spending days manually reading hundreds of stored procedures before a database migration — **SP Migration Companion eliminates that.**

Upload your `.sql` files. In seconds, get:

- Every **physical table** referenced across all procedures — with schema, CRUD operations, and aliases
- Every **column** mapped to its table — including multi-word bracketed names like `[Customer ID]`
- **Schema breakdown** — see exactly which schemas are touched and in what order to migrate
- **AI migration risk report** — Mistral-7B analyzes your extraction and generates a plain-English risk assessment with recommended migration order

What used to take a team of BSAs two weeks now takes **30 seconds**.

---

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│        index.html           │        │       main.py (FastAPI)      │
│   (Browser — any device)    │◄──────►│     Deployed on Render       │
│                             │  REST  │                              │
│  • File upload UI           │        │  POST /analyze               │
│  • 5-tab results display    │        │    → SQL parser engine       │
│  • Excel download           │        │    → returns JSON            │
│  • AI insights checkbox     │        │                              │
└─────────────────────────────┘        │  POST /ai-insights           │
                                       │    → HuggingFace API         │
                                       │    → Mistral-7B-Instruct     │
                                       └──────────────────────────────┘
```

**Key design decision:** The Python parser lives entirely in the FastAPI backend on Render. The UI is a single static HTML file — zero framework, zero build step, works offline (for analysis) or pointed at any backend URL. Change the parser logic without touching the UI.

---

## Features

### Core Parser Engine
- **Deterministic regex + AST-aware extraction** — same result every run, no LLM guessing
- **CTE chain resolution** — traces `alias → CTE → physical table` across multiple hops
- **Alias collision fix** — aliases scoped per-statement, so `o` in different JOINs resolves correctly
- **Bracketed multi-word column names** — `[Customer ID]`, `[Credit Risk Rating]` handled correctly
- **Multi-encoding support** — UTF-8, Windows-1252 (SSMS default), CP1252, Latin-1
- **Multi-dialect** — T-SQL, PostgreSQL, MySQL, Oracle PL/SQL auto-detected

### What gets extracted
| Item | Detail |
|---|---|
| Physical tables | Schema, base name, full reference |
| Operations | SELECT / INSERT / UPDATE / DELETE / MERGE / TRUNCATE per table |
| Column names | Mapped to table via alias or direct reference |
| Table aliases | Per-statement alias resolution |
| Dynamic SQL | Flagged for manual review |
| CTEs | Resolved to source physical tables — excluded from output as non-physical |
| Temp tables | Excluded from output as non-physical |

### UI (index.html)
- **5 tabs** — Summary, Physical Tables, Columns Detail, Schema Breakdown, AI Insights
- **Live search + filter** — by schema, operation type, column name
- **Sortable columns** — click any table header
- **Download Excel** — 5-sheet workbook matching all tabs
- **API endpoint bar** — point the UI at any backend (local dev or Render production)
- **AI Insights checkbox** — opt-in per session, choose to focus on a specific procedure

### AI Insights (HuggingFace Mistral-7B)
- Sends extracted table/schema/operation metadata to Mistral-7B-Instruct
- Returns: migration complexity rating, top 3 risks, recommended migration order, watch points
- Completely optional — checkbox-gated, never runs without user intent
- Model: `mistralai/Mistral-7B-Instruct-v0.2` via HuggingFace Inference API (free tier)

---

## Quick Start

### 1. Clone
```bash
git clone https://github.com/your-org/sp-migration-companion
cd sp-migration-companion
```

### 2. Backend — local
```bash
pip install -r requirements.txt

# Optional: set HuggingFace token for AI insights
export HF_TOKEN=hf_your_token_here

uvicorn main:app --reload
# API running at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 3. Frontend
Open `index.html` in any browser. Set the API endpoint to `http://localhost:8000`.

That's it. No npm, no build step, no Docker required for local dev.

---

## Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo — Render auto-detects `render.yaml`
4. Add environment variable: `HF_TOKEN` = your HuggingFace token
5. Deploy — takes ~2 minutes

Update `index.html`'s default API URL to your Render URL:
```html
<input ... value="https://sp-migration-companion-api.onrender.com" ... />
```

Or host `index.html` on GitHub Pages / Netlify / S3 — it's a single static file.

---

## API Reference

### `GET /health`
Returns service status and HuggingFace configuration state.
```json
{ "status": "ok", "hf_configured": true }
```

### `POST /analyze`
**Body:** `multipart/form-data` — one or more `.sql` files as `files[]`

**Returns:**
```json
{
  "status": "success",
  "stats": {
    "total_procedures": 3,
    "total_tables": 11,
    "total_schemas": 5,
    "total_columns": 42,
    "dynamic_sql_count": 1
  },
  "procedures": [
    { "name": "sales.usp_ProcessOrders", "file": "report.sql",
      "dialect": "T-SQL (SQL Server)", "is_dynamic": false,
      "table_count": 5, "col_count": 12 }
  ],
  "tables": [
    { "proc": "sales.usp_ProcessOrders", "schema": "DBO",
      "table": "CUSTOMERS", "ops": "SELECT", "aliases": "c" }
  ],
  "columns": [
    { "proc": "sales.usp_ProcessOrders", "schema": "DBO",
      "table": "CUSTOMERS", "col": "CustomerName", "ops": "SELECT" }
  ],
  "schema_map": {
    "DBO": {
      "CUSTOMERS": { "ops": "SELECT", "cols": ["CustomerName","Email"], "procs": ["sales.usp_ProcessOrders"] }
    }
  }
}
```

### `POST /ai-insights`
**Body:** JSON — the `procedures`, `tables`, `columns`, `schema_map` from `/analyze`, plus optional `focus_proc`

**Returns:**
```json
{
  "status": "success",
  "insight": "MIGRATION COMPLEXITY: High\n\nTOP 3 RISKS:\n1. ...",
  "model": "mistralai/Mistral-7B-Instruct-v0.2",
  "focus": "sales.usp_ProcessOrders"
}
```

**Note:** Requires `HF_TOKEN` environment variable. Returns HTTP 503 if not configured.

---

## Project Structure

```
sp-migration-companion/
├── main.py              # FastAPI backend — SQL parser + AI insights endpoints
├── requirements.txt     # Python dependencies
├── render.yaml          # Render deployment config
├── index.html           # Single-file UI — points to backend via configurable URL
├── .env.example         # Environment variable template
└── README.md
```

---

## SQL Parser — How It Works

The parser uses a **4-stage pipeline**:

```
Raw SQL bytes
    │
    ▼
1. ENCODING       → try utf-8 → windows-1252 → latin-1 (never drops content)
    │
    ▼
2. NORMALIZE      → strip comments → normalize whitespace
                  → replace [Multi Word Names] → MULTI_WORD_NAMES (track mapping)
    │
    ▼
3. EXTRACT        → collect CTE names + map each CTE to its source physical table
                  → split into DML statements (SELECT / INSERT / UPDATE / DELETE / MERGE)
                  → per-statement alias map (fixes alias collision across statements)
                  → resolve CTE alias chains → physical table
                  → extract qualified (alias.col) and unqualified columns
    │
    ▼
4. RESTORE        → map MULTI_WORD_NAMES back to "Multi Word Names" display form
                  → deduplicate raw + display forms
                  → return structured JSON
```

**Why not use an LLM for parsing?**
LLMs produce different results each run, miss tables depending on prompt phrasing, and hallucinate column names. The deterministic regex engine produces identical output every time and can be unit-tested.

**Why not use sqlparse/sqlglot?**
Both struggle with T-SQL-specific patterns (CTE chains, bracketed names with spaces, `WITH (NOLOCK)`), especially in SSMS-generated files. The custom engine handles these explicitly.

---

## Known Limitations

| Limitation | Reason |
|---|---|
| Dynamic SQL (`EXEC()`, `sp_executesql`) | Table names are runtime strings — static analysis cannot resolve them |
| Multi-hop CTE chains (CTE → CTE → table) | Partial resolution — single-hop chains resolve fully |
| Columns in multi-table SELECT without alias prefix | Cannot determine which table without executing the SQL |

All limitations are flagged in the output — nothing is silently dropped.

---

## Roadmap

- [ ] Migration dependency graph — visual showing which procedures share tables
- [ ] Complexity score per procedure (Low / Medium / High) based on table count × schema count × op types
- [ ] AWS Bedrock integration (Claude/Titan) for deeper AI analysis
- [ ] Batch Excel output — one workbook per uploaded file
- [ ] QueryTuner integration — SP analysis as a module within querytuner.com

---

## Contributing

PRs welcome. The parser engine (`main.py`) and UI (`index.html`) are intentionally kept separate — you can improve the parser without touching the UI and vice versa.

```bash
# Run tests (add your .sql files to /test_files/)
python -m pytest tests/

# Local dev with hot reload
uvicorn main:app --reload --port 8000
```

---

## License

MIT — see [LICENSE](LICENSE)

<!-- Built by [Sajja](https://github.com/sql-sp-companion) · [querytuner.com](https://querytuner.com) · [autoshiftops.com](https://autoshiftops.com) -->