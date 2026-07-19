<div align="center">

# 🔍 sql-sp-companion

**Every other database migration tool needs a database connection or a credit card.**
**This one needs a folder of `.sql` files.**

Drop your stored procedures in a browser. Get every physical table, schema,
column and CRUD operation in 30 seconds — plus an optional AI migration risk
report. No install. No agent. No IAM role. No database credentials.

[![CI](https://img.shields.io/github/actions/workflow/status/AutoShiftOps/sql-sp-companion/ci.yml?style=flat-square&label=tests)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Code of Conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa?style=flat-square)](CODE_OF_CONDUCT.md)

[**Live demo**](https://sql-sp-companion.vercel.app) · [Why this exists](#why) · [What's in / what's out](#whats-in--whats-out)

*A [QueryTuner](https://querytuner.com) project*

<!-- demo.gif goes here: 15-second loop of upload → tabs → Excel download -->

</div>

---

## Why

Every database migration starts with one question: **what does this code
actually touch?** Answering it means a Business Solution Architect reading
stored procedures by hand — hundreds of them, for weeks — and humans miss things.

The tools that automate this all assume something you may not have:

| Tool | What it needs first | The question it answers |
|---|---|---|
| AWS SCT | A live DB connection + AWS account | *Will this convert to Aurora?* |
| AWS DMS Fleet Advisor | A collector, S3 bucket, IAM roles, DB creds | *What's in my fleet?* — **retired May 2026** |
| SQLFlow / GSP | A commercial licence | *Where does this data flow?* |
| sqlglot | Nothing — but [falls back to `Command` mode on T-SQL procedure bodies](https://www.dpriver.com/blog/gsp-vs-jsqlparser-vs-sqlglot-sql-parser-comparison-2026/), losing all structure inside them | *Parse this query* |
| **sql-sp-companion** | **A folder of `.sql` files** | ***What does my migration wave touch?*** |

AWS retired Fleet Advisor — a **free** tool, from AWS — in May 2026. Look at
what it asked for before it would tell you anything: install a data collector,
create an S3 bucket, CloudFormation an IAM stack, provision database users. That
is a six-week security review to run an *assessment*, before anyone has approved
the migration. Friction killed it, not competition.

This tool is the inverse of everything that killed it. If you have a Git repo
full of `.sql` and no production credentials — the normal situation for a BSA
scoping work — this is built for exactly that moment.

**Deterministic, not generative.** Same input, same output, every run. An LLM
gives you a different answer each session; you cannot put that in a migration
plan and defend it in a review.

## Try it

**Hosted:** [sql-sp-companion.vercel.app](https://sql-sp-companion.vercel.app) — the
backend is on a free tier, so the first request after an idle period takes
~30–60s to wake. Subsequent requests are instant.

**Local (recommended, and the point of the tool — your SQL never leaves your machine):**

## Quickstart (60 seconds, local)

```bash
git clone https://github.com/AutoShiftOps/sql-sp-companion
cd sql-sp-companion
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `index.html` in your browser. The API bar defaults to
`http://localhost:8000`. Click **Try demo SQL → Analyze**. Done.

> Or run `./start.sh` which does all of the above.

## What you get

| Tab | Contents |
|---|---|
| 📋 **Summary** | Per-procedure stats, dialect, dynamic SQL warnings |
| 🗂 **Physical Tables** | Schema · table · CRUD ops · aliases — filterable, sortable |
| 📐 **Columns Detail** | Every column mapped to its table, incl. `[Multi Word]` names |
| 🏗 **Schema Breakdown** | Schema → tables → columns, with owning procedures |
| ✨ **AI Insights** (opt-in) | Migration complexity, top risks, recommended order |

Plus **⬇ Download Excel** — a 5-sheet workbook of everything above, stamped
with tool version and timestamp for audit trails.

## What the parser handles

- **Dialects:** T-SQL, PostgreSQL, MySQL, Oracle PL/SQL (auto-detected)
- **Encodings:** UTF-8, Windows-1252/CP1252 (SSMS default), Latin-1 — bad bytes
  mid-file never silently drop content
- **CTE chains:** `alias → CTE → physical table` resolution (single-hop; deeper chains are a documented limitation, KL-3)
- **Alias collision:** `o` meaning different tables in different statements —
  aliases are scoped per-statement
- **Bracketed names:** `[Party ID]`, `[Regional Risk Rating]` survive as
  single columns
- **Exclusions by design:** temp tables (`#t`) and CTE names never appear in
  output — they are not physical schema objects

## What's in / what's out

Read this before you invest an afternoon. We would rather lose you here than
waste your time.

### ✅ In scope — what this does well

- **Physical table inventory** per stored procedure: schema, table, CRUD ops, aliases
- **Column-to-table mapping**, including `[Bracketed Multi Word]` identifiers
- **Schema breakdown** — which schemas are in play, which procedures own which tables
- **CTE resolution** — traces `alias → CTE → physical table` (single hop, reliably)
- **Alias collision handling** — `o` meaning different tables in different statements
- **Encoding survival** — UTF-8, Windows-1252/CP1252 (SSMS default), Latin-1. Bad bytes never truncate a file
- **Dialects** — T-SQL, PostgreSQL, MySQL, Oracle PL/SQL (auto-detected)
- **Excel export** — 5 sheets, version + timestamp stamped for audit trails
- **Optional AI risk narrative** — opt-in, your own token, metadata only
- **Runs offline** — the parser makes zero network calls, ever

### ❌ Out of scope — deliberately, permanently

- **Not a converter.** It will not rewrite T-SQL into PL/pgSQL. Use AWS SCT — it is free and good at that.
- **Not a lineage platform.** It will not draw source→target column flow diagrams across your estate. Use SQLFlow or Dataedo.
- **Not a data catalogue.** No governance, no PII classification, no stewardship workflow.
- **Never connects to a database.** By design. Files in, report out. If you need live schema resolution or `SELECT *` expansion, this is the wrong tool and always will be.
- **Never executes your SQL.** Which is why dynamic SQL is a hard boundary, not a bug (see KL-4).
- **Not a formatter, linter, or optimiser.** For query performance, that's [QueryTuner](https://querytuner.com).

### 🚧 In scope but not built yet

- Migration dependency graph (which procedures share tables → sequencing)
- Batch CLI for estate-scale runs
- AST backend for the SELECT-list parsing that fixes KL-3

## How the parser works

```
Raw SQL bytes
    │
    ▼
1. ENCODING    → utf-8 → windows-1252 → latin-1, whole buffer first
                 (never partial, never drops content after a bad byte)
    │
    ▼
2. NORMALIZE   → strip block + line comments
                 → MASK STRING LITERAL CONTENTS  ← or 'text FROM dbo.X' invents a table
                 → [Multi Word Names] → MULTI_WORD_NAMES (mapping retained)
    │
    ▼
3. EXTRACT     → collect CTE names + map each CTE to its source physical table
                 → split into DML statements (SELECT/INSERT/UPDATE/DELETE/MERGE)
                 → build a PER-STATEMENT alias map  ← fixes alias collision
                 → resolve CTE alias → physical table
                 → extract qualified (alias.col) and unqualified columns
    │
    ▼
4. RESTORE     → MULTI_WORD_NAMES → "Multi Word Names" display form
                 → deduplicate raw + display forms
                 → structured JSON
```

**Why not an LLM?** LLMs return different results each run, miss tables depending
on prompt phrasing, and hallucinate column names. You cannot put that in a
migration plan and defend it in a review. This engine returns identical output
for identical input, and that property is [asserted by a test](tests/test_contracts.py).

**Why not sqlglot?** It was the first thing I tried. Given a T-SQL stored
procedure it [falls back to parsing the body as an opaque `Command`](https://www.dpriver.com/blog/gsp-vs-jsqlparser-vs-sqlglot-sql-parser-comparison-2026/) —
TRY/CATCH, DECLARE and control flow simply aren't in the tree. General SQL Parser
handles it and is commercial. So parsing *inside* T-SQL procedure bodies is
free-but-falls-back or works-but-costs-money. A hand-built engine is normally the
wrong answer; here it's the only free one. (A hybrid — regex to split statements,
sqlglot for the SELECT lists — is the v1.2 roadmap item and would fix KL-3.)

## Honest limitations

Each one is pinned by a strict-xfail test in
[`tests/test_known_limitations.py`](tests/test_known_limitations.py) — the day
one gets fixed, CI turns red and forces this table to be updated. This list
cannot silently rot.

| ID | Limitation | Why |
|---|---|---|
| **KL-2** | Casing differs between `[Bracketed]` and plain identifiers | Cosmetic; v1.1 |
| **KL-3** | Multi-hop CTE chains (CTE→CTE→table) resolve partially | Needs AST backend |
| **KL-4** | Dynamic SQL (`EXEC`, `sp_executesql`) tables not extracted | **Permanent by design.** Table names are runtime strings. Flagged ⚠, never guessed |
| **KL-5** | Expression-derived CTE output columns (`SUM(Amount) AS 'Total'`) don't surface the real column read inside the expression | Never invents the alias as a column (correct) — but doesn't yet parse into simple aggregate expressions either. Needs expression parsing |
| **KL-6** | A column referenced through a CTE alias is attributed even when the CTE never outputs a column by that name | Needs a per-CTE output allow-list, not just alias→source translation (KL-1's fix) |
| **KL-7** | ⚠️ A physical table is dropped from the report entirely when its base name collides with a same-named CTE (e.g. a CTE named `Country` hides `dbo.Country`) | The CTE-exclusion check compares bare base names only, across all schemas. **Most severe limitation on this list** — a table silently missing, not a column |

Nothing is silently dropped — everything the parser can't resolve is labeled as
such in the output. We would rather show you a gap than invent a table.

## Free tier

Apache-2.0, self-hosted, no signup:

| | Free | Enterprise |
|---|---|---|
| Files per request | 5 | unlimited |
| Size per file / request | 1 MB / 5 MB | 100 MB / 2 GB |
| Distinct tables reported | 50 | unlimited |
| AI insights (your own HF token) | ✅ | ✅ |
| Batch CLI, hosted service, SLA, support | ❌ | ✅ |
| Purview / Collibra export, air-gapped AI | ❌ | ✅ |

The limits live in [`limits.py`](limits.py) under Apache-2.0 — **you can legally
fork and delete them.** We know. [LICENSING.md](LICENSING.md) explains why they
exist anyway and where the real commercial value sits (hint: not in the
constants). Current limits are always discoverable at `GET /health`.

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│        index.html           │        │       main.py (FastAPI)      │
│   (Browser — any device)    │◄──────►│   Render / your own VPC      │
│                             │  REST  │                              │
│  • File upload UI           │        │  GET  /health                │
│  • 5-tab results display    │        │    → version, tier, limits   │
│  • Excel download           │        │                              │
│  • AI insights checkbox     │        │  POST /analyze               │
│  • Configurable API URL     │        │    → parser engine (offline) │
└─────────────────────────────┘        │    → returns JSON            │
                                       │                              │
                                       │  POST /ai-insights  (opt-in) │
                                       │    → HuggingFace (Qwen2.5)   │
                                       └──────────────────────────────┘
```

The UI and parser are deliberately decoupled: change the Python engine without
touching the UI, or restyle the UI without touching the parser. The UI's API
bar points at any backend — localhost, Render, or your own VPC.

## Deploy

**Render (reference deployment):** push to GitHub → New Web Service → Render
auto-detects `render.yaml` → set `HF_TOKEN` env var (optional, enables AI).
Note: free-tier instances cold-start (~30–60s) after idle.

**Anywhere else:** it's one FastAPI app. `uvicorn main:app` behind any reverse
proxy. **Before production: restrict CORS `allow_origins` in `main.py` to your
UI's domain** (see [SECURITY.md](SECURITY.md)).

## API

Interactive docs at `/docs` (Swagger) when the backend is running.

- `GET /health` → `{"status":"ok","version":"1.0.0","hf_configured":true}`
- `POST /analyze` — multipart `.sql` files → JSON with `meta` (version,
  timestamp, files), `procedures`, `tables`, `columns`, `schema_map`, `stats`
- `POST /ai-insights` — analysis JSON (+ optional `focus_proc`) → risk
  narrative. Requires `HF_TOKEN`; returns 503 otherwise.

## Testing

```bash
pytest tests/ -v          # 68 passing, 4 tracked limitations
```

Five layers, all CI-gated on every PR — see **[TEST_PLAN.md](TEST_PLAN.md)**:

| Layer | Guards |
|---|---|
| **Contracts** | 6 promises incl. determinism, never-invent, zero network calls in parsing |
| **Golden files** | Committed output snapshots — any behaviour change fails with a structured diff |
| **Known limitations** | `xfail(strict)` — fixing one turns CI **red**, forcing the docs to update |
| **Tiers** | The free/paid boundary can't move by accident |
| **API** | JSON contract the UI depends on |

The golden-file gate is how "does my change break existing features?" gets
answered mechanically rather than by hope. A parser PR with no golden diff
changed nothing; a PR *with* one must explain it.

**The best way to contribute is a failing SQL snippet** — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- **v1.1** — batch CLI (`spcompanion analyze ./sql-dir/`), PyPI package,
  per-extraction confidence scores
- **v1.2** — pluggable AI backends (AWS Bedrock, local Ollama for air-gapped
  environments), migration dependency graph
- **v2.0** — QueryTuner integration: SP analysis as the migration-planning
  module of [querytuner.com](https://querytuner.com)

## Contributing · Conduct · Security

[CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md) · [TEST_PLAN.md](TEST_PLAN.md) · [LICENSING.md](LICENSING.md)

## License

[Apache-2.0](LICENSE) © 2026 AutoShiftOps — see [LICENSING.md](LICENSING.md) for the commercial model

---

<div align="center">

Built by [Sajja](https://autoshiftops.com) · [querytuner.com](https://querytuner.com)

</div>
