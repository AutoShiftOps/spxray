# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [SemVer](https://semver.org/).

## [1.0.0] — Unreleased

First public release.

### Added
- Deterministic SQL parser: physical tables, columns, CRUD ops, aliases per stored procedure
- CTE chain resolution (single-hop) and per-statement alias scoping
- `[Bracketed Multi Word]` identifier support
- Multi-encoding reader — UTF-8, UTF-16 (BOM-detected), Windows-1252, CP1252, Latin-1
- Dialect auto-detection — T-SQL, PostgreSQL, MySQL, Oracle PL/SQL
- FastAPI backend: `GET /health`, `POST /analyze`, `POST /ai-insights`
- Single-file browser UI with 5 tabs and Excel export (SheetJS)
- Opt-in AI migration risk narrative via HuggingFace (Qwen2.5-Coder)
- Report metadata (tool version, UTC timestamp, tier) on every response
- Free/enterprise tier limits (`limits.py`)
- Five-layer test suite — 91 tests, 9 tracked limitations ([TEST_PLAN.md](TEST_PLAN.md))
- Six new fixture-corpus additions targeting hard structural patterns: `CROSS
  APPLY`/`OUTER APPLY`, recursive CTEs, `MERGE ... OUTPUT INTO`, 3-level
  nested derived-table subqueries, a second CTE/table name-collision variant,
  and a UTF-16-with-BOM encoded file

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
- **KL-11: UTF-16 files no longer decode into silent, empty-success garbage.**
  `read_bytes_safe` now detects a UTF-16 BOM (`\xff\xfe` LE / `\xfe\xff` BE)
  and decodes with the `utf-16` codec (which auto-detects endianness) before
  falling back to the utf-8/windows-1252/cp1252/latin-1 chain. Previously,
  utf-8 decoding of UTF-16 bytes didn't raise — most ASCII-range UTF-16LE
  bytes are individually valid UTF-8, so it silently "succeeded" into
  NUL-interleaved garbage that failed every parser regex, returning a
  confident-looking **empty** report for a file that was never actually
  empty. A new contract test (`test_C3_utf16_file_never_returns_empty_success`)
  pins the guarantee this closes: a UTF-16 file must either parse correctly
  or raise a clear error — it may never silently succeed with nothing in it.

### Known limitations
See [README](README.md#honest-limitations). Each is pinned by a strict-xfail test.

**Known issue — table-level, not cosmetic (KL-7):** if a CTE shares its name
with a physical table (e.g. `WITH Country AS (...)` alongside a real
`dbo.Country`), **the physical table is dropped from the report entirely**,
with no warning. The exclusion check that keeps CTE names out of the table
list (required for C2) matches on bare base name only, across all schemas —
so it also excludes any genuinely different table that happens to share that
name. **Confirmed via the fixture corpus batch below to generalize**: it drops
*any* table sharing that name anywhere in the procedure, even one referenced
in a completely unrelated statement with no relationship to the colliding CTE.
This is more serious than KL-1/KL-6/KL-8 (wrong or missing columns): a table
a migration plan needs to know about can be silently absent, indistinguishable
from "this procedure never touches it." Avoid naming CTEs after real tables
until KL-7 is fixed.

**Known issues — table-level, from the fixture-corpus growth batch:**
- **KL-9**: `MERGE target AS tgt` / `USING source AS src` never resolve their
  aliases (a regex bug for MERGE, a missing keyword for USING) — both tables
  are correctly registered as touched, but end up with **zero columns each**,
  silently.
- **KL-10**: `OUTPUT ... INTO auditTable` is not recognized by any table
  pattern — the audit table being written to **never appears in the report
  at all**, same severity as KL-7.
- **KL-8** (narrower, column-level like KL-1/KL-6 — same defect class: see its
  test docstring): `CROSS APPLY`/`OUTER APPLY` aliases, and a recursive CTE's
  self-reference to its own CTE-computed column, can leak a column from an
  unrelated source onto whichever single physical table is in scope for that
  statement.

KL-11 (UTF-16 silently producing an empty report) is now fixed — see Fixed,
above.
