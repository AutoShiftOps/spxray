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
- Five-layer test suite — 95 tests, 6 tracked limitations ([TEST_PLAN.md](TEST_PLAN.md))
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
- **KL-8: a single-table fallback no longer overrides the qualified pass's
  correct refusals.** `CROSS APPLY`/`OUTER APPLY` aliases and a recursive
  CTE's own self-referencing computed column (e.g. `oc.Depth` from
  `0 AS Depth` in the anchor member) used to leak onto whichever one
  physical table was in scope, because the "unqualified SELECT, single
  table only" fallback tokenized the SELECT list independently and blindly
  stripped every alias prefix via `token.split('.')[-1]` — including
  references the qualified-columns pass, moments earlier in the same
  statement, had already correctly declined to resolve. The fallback now
  tracks and respects those declines. Fixing this exposed a second, older
  bug in the same area: `build_alias_map`'s alias-detection regex never
  matched a statement like `SELECT p.Col FROM t p;` (alias immediately
  before a semicolon, no trailing `WHERE`) — the lookahead had no semicolon
  alternative. Previously invisible because the (now-removed) fallback
  redundancy silently compensated for it; closing the semicolon gap was
  the fix that made the KL-8 fix actually hold rather than regressing
  `alias_collision.sql`/`crud_and_dynamic.sql`. Same defect class as KL-1.
- **KL-9: `MERGE target AS tgt` / `USING source AS src` aliases now
  resolve.** Two regex bugs in `build_alias_map`: the MERGE branch required
  two consecutive whitespace matches that ordinary single-spaced `MERGE
  table` syntax never satisfies, and `USING` wasn't in the alias-detection
  keyword list at all. A third, separate defect in `STMT_SPLIT` also had to
  be fixed for this to fully resolve: it split a MERGE's own `WHEN MATCHED
  THEN UPDATE SET ...` sub-clause into its own statement chunk, severing it
  from the `tgt`/`src` aliases declared in the MERGE header — so even with
  the alias-regex fixed, `tgt.Name`/`src.Name` stayed unresolved until
  `STMT_SPLIT` stopped splitting immediately after `THEN `.
- **KL-10: `OUTPUT ... INTO auditTable` now registers the audit table.** No
  `TABLE_OP_PATTERNS` entry recognized `OUTPUT ... INTO`, so a table
  genuinely written to by every MERGE/UPDATE/DELETE using this common
  audit-logging pattern was silently absent from the report. Registered as
  an INSERT-target table now (its column list from the `INTO table
  (col_list)` clause is not parsed — out of scope for this fix, a future
  KL if ever needed).

### Known limitations
See [README](README.md#honest-limitations). Each is pinned by a strict-xfail test.

**Known issue — table-level, not cosmetic (KL-7):** if a CTE shares its name
with a physical table (e.g. `WITH Country AS (...)` alongside a real
`dbo.Country`), **the physical table is dropped from the report entirely**,
with no warning. The exclusion check that keeps CTE names out of the table
list (required for C2) matches on bare base name only, across all schemas —
so it also excludes any genuinely different table that happens to share that
name. **Confirmed via the fixture corpus batch to generalize**: it drops *any*
table sharing that name anywhere in the procedure, even one referenced in a
completely unrelated statement with no relationship to the colliding CTE.
This is more serious than KL-1/KL-6 (wrong or missing columns): a table a
migration plan needs to know about can be silently absent, indistinguishable
from "this procedure never touches it." Avoid naming CTEs after real tables
until KL-7 is fixed.

KL-2 through KL-6 and KL-7b remain documented, honest edge cases — see the
README table for what each one is and why it hasn't been fixed yet.
