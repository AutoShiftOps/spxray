# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [SemVer](https://semver.org/).

## [1.0.0] — Unreleased

First public release.

### Added
- Deterministic SQL parser: physical tables, columns, CRUD ops, aliases per stored procedure
- CTE chain resolution (single-hop) and per-statement alias scoping
- `[Bracketed Multi Word]` identifier support
- Multi-encoding reader — UTF-8, Windows-1252, CP1252, Latin-1
- Dialect auto-detection — T-SQL, PostgreSQL, MySQL, Oracle PL/SQL
- FastAPI backend: `GET /health`, `POST /analyze`, `POST /ai-insights`
- Single-file browser UI with 5 tabs and Excel export (SheetJS)
- Opt-in AI migration risk narrative via HuggingFace (Qwen2.5-Coder)
- Report metadata (tool version, UTC timestamp, tier) on every response
- Free/enterprise tier limits (`limits.py`)
- Five-layer test suite — 77 tests, 6 tracked limitations ([TEST_PLAN.md](TEST_PLAN.md))

### Fixed
- **String literals are now masked before extraction.** Previously
  `WHERE Notes = 'migrated FROM dbo.Phantom'` invented a table that does not
  exist, violating the never-invent contract. The same bug caused tables to be
  scraped out of dynamic SQL string literals while simultaneously flagging that
  SQL as unanalyzable — two claims that cannot both be true.
- **KL-1: CTE output aliases are no longer reported as physical columns.**
  `SELECT Id AS 'Party ID' FROM dbo.Party` means dbo.Party has a column `Id`,
  not `Party ID` — the alias is now translated back to its real source column
  (`extract_cte_output_map` in `main.py`) instead of being reported as if it
  were a real column, including when the source is on a JOINed table within
  the CTE, not just the CTE's own primary FROM table. Expression-derived
  output columns (`CASE ... END AS 'X'`, `COUNT(*) AS 'Total'`) have no single
  source column, so they are dropped rather than invented (see KL-5). Fixing
  this also surfaced a second bug in the same code path: single-word
  bracketed columns (e.g. `[DerivedRiskOutcome]`) were being silently
  deduplicated against themselves and dropped from the report entirely —
  that dedup logic is now scoped to genuine multi-word display forms only.

### Known limitations
See [README](README.md#honest-limitations). Each is pinned by a strict-xfail test.

**Known issue — table-level, not cosmetic (KL-7):** if a CTE shares its name
with a physical table (e.g. `WITH Country AS (...)` alongside a real
`dbo.Country`), **the physical table is dropped from the report entirely**,
with no warning. The exclusion check that keeps CTE names out of the table
list (required for C2) matches on bare base name only, across all schemas —
so it also excludes any genuinely different table that happens to share that
name. This is more serious than KL-1/KL-6 (wrong or missing columns): a table
a migration plan needs to know about can be silently absent, indistinguishable
from "this procedure never touches it." Avoid naming CTEs after real tables
until KL-7 is fixed.
