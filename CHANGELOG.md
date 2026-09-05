# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [SemVer](https://semver.org/).

## [Unreleased]

Working through the open GitHub issue backlog after v1.1.0.

### Fixed
- **#11 — KL-2:** bracketed and plain table names now share one casing
  convention (uppercase); bracket display-case is no longer restored onto
  `schema`/`base` (columns are unaffected — their multi-word display
  preservation is intentional)
- **#15 — KL-6:** a column referenced through a CTE alias is no longer
  attributed to the CTE's source table unless the CTE actually outputs a
  column by that name (new per-CTE allow-list, `SELECT *` CTEs left
  unenforced since their real columns are unknowable statically)
- **#16, #17 — KL-7/KL-7b:** a physical table sharing a bare name with a CTE
  (e.g. `dbo.Country` next to `WITH Country AS (...)`) is no longer dropped
  from the report — the exclusion check now only applies to unqualified
  (bare) CTE references, never a schema-qualified real table
- **#24:** corrected the C2 contract test in `test_contracts.py`, which had
  encoded the KL-7/KL-7b bug itself ("no table's bare name may ever equal a
  CTE name") as a passing assertion. Narrowed to the real invariant: an
  unqualified CTE-name reference is never reported as a table
- `test_KL3`'s fixture rewritten to remove an accidental confound (it named
  its own CTE `Country` while also directly joining a real `dbo.Country`,
  which the KL-7 fix incidentally "resolved" for the wrong reason); the real
  multi-hop gap it's meant to test is confirmed still open

### Added
- Issue #23: on-page result tables (Physical Tables/Columns Detail/Schema
  Breakdown) now match the Excel export's operation-color palette exactly
  (three of six colors were previously only approximated) and carry
  accent-styled headers and stronger row striping
- Issue #20: a coarse "coverage" score — % of procedures fully understood
  (not dynamic SQL, every table resolved at least one column) vs. needing
  manual review, with a plain-English reason per flagged procedure. Built
  entirely from data already tracked (`is_dynamic`, per-table column
  resolution); no new parser instrumentation. Surfaced as a new `coverage`
  field on `/analyze`, a Summary-tab card + per-procedure badges, and a
  banner row + "Needs Review" column in the Excel Summary sheet

### Closed without code
- **#4** — closed; substantially served by the existing Excel export + AI
  Insights narrative rather than a third documentation format
- **#19** — a contribution template, not a feature; nothing to implement

## [1.1.0] — 2026-09-04

Note: an earlier `v1.0.0` tag/release ("First release cycle pre-enterprise",
2026-07-21) already exists on an older commit predating everything below —
this section was originally drafted as "1.0.0 — Unreleased" before that
collision was found, hence the version bump rather than a rename of history
already public. Feature-complete UI/UX pass and parser-contract fixes
building on that initial publish.

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
- Five-layer test suite — 106 tests, 8 tracked limitations ([TEST_PLAN.md](TEST_PLAN.md))
- Six new fixture-corpus additions targeting hard structural patterns: `CROSS
  APPLY`/`OUTER APPLY`, recursive CTEs, `MERGE ... OUTPUT INTO`, 3-level
  nested derived-table subqueries, a second CTE/table name-collision variant,
  and a UTF-16-with-BOM encoded file
- Paste-SQL input mode alongside file upload, with four labeled demo examples
  (simple, multi-CTE, MERGE+audit, cross-schema CRUD) sourced from the test fixtures
- GitHub link + live star-count button and a "New Analysis"/live-count start
  flow in the header
- Excel export rebuilt on ExcelJS: navy header bars, blue/white zebra
  striping, per-operation color-coding, a Legend sheet, and auto-fit columns
  — ported from the original `sp_analysis_v2.xlsx` visual language
- Client-side paste-size guard mirroring the free tier's 5 MB limit, shown
  inline before Analyze is clickable
- Cold-start messaging for the free Render backend: a spinner + "waking up"
  notice appears once `/health` or `/analyze` runs past ~2s, distinct from a
  genuinely-unreachable-backend message, and clears cleanly once resolved
- The "API Endpoint" bar (URL + Connected/HF status) collapsed behind a ⚙
  toggle in the header, with a small always-visible status dot, so a
  first-time visitor's first impression is the hero + upload box
- `<meta>` description, Open Graph, and Twitter Card tags, plus a hardened
  favicon (SVG + PNG fallbacks, reusing the existing brand mark) so shared
  links render a real preview
- Mobile (375px) layout fixes, keyboard-accessible schema-table toggles,
  visible focus outlines, and an explicit empty-state message when a file
  contains no physical tables (only temp tables/CTEs)
- Roadmap/issue-triage pass: every known limitation (KL-2 through KL-15) and
  several post-1.0 enhancement ideas filed as tracked GitHub issues

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
- **KL-12: `AS target`/`AS source` MERGE aliases now resolve.** `TARGET` and
  `SOURCE` are real MERGE keywords (`WHEN MATCHED BY TARGET`), so
  `SKIP_WORDS` correctly denylisted them as bare table/column names — but
  that same denylist also rejected them as *alias* names, silently breaking
  the single most common MERGE-aliasing convention (it's what Microsoft's
  own MERGE docs use; KL-9 was only ever exercised with `tgt`/`src`). Fixed
  with a narrower `ALIAS_SKIP_WORDS` set, used only at the two
  alias-validity checks in `build_alias_map` — every other `SKIP_WORDS`
  check (table names, column names, unqualified tokens) is untouched.
- **KL-13: `INSERT INTO tbl (col1, col2, ...)` target column lists are now
  captured.** The explicit column list on an INSERT's target — the single
  most common write pattern in stored procedures — was never wired into any
  extraction pass; only the source-side `SELECT` list was. Unambiguous by
  construction (no alias or single-table heuristic needed), so it's
  attributed directly. Also covers a MERGE's own
  `WHEN NOT MATCHED THEN INSERT (col_list)`, whose implicit target is the
  MERGE header's own table.
- **KL-14: unqualified columns in a single-table `DELETE ... WHERE` are now
  captured.** Per the pipeline's own single-table-only rule this was
  unambiguous, but `DELETE` was never routed through the unqualified-column
  pass at all — only `SELECT ... FROM` was. The shared tokenizing/filtering
  logic was factored into `_attribute_unqualified_tokens` so both passes
  apply identical rules.
- **Phantom `SELECT` op on `DELETE` statements removed.** A generic
  `\bFROM\s+table` pattern in `TABLE_OP_PATTERNS` (meant for plain
  `SELECT ... FROM`) also matched a `DELETE FROM table`'s own `FROM`
  clause, tagging a `SELECT` op that never happened anywhere in the SQL —
  a never-invent violation on the *ops* list, not just columns. Now
  excluded via `(?<!DELETE\s)`; a genuine `SELECT` elsewhere on the same
  table is unaffected (`test_C4_delete_inside_larger_procedure_still_gets_only_delete`).

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

**New — KL-15:** found while fixing KL-12/KL-13. A MERGE's `USING (SELECT
...) AS src` derived table has its own `SELECT` keyword, which `STMT_SPLIT`
treats as a statement boundary the same way it used to split a MERGE's own
`WHEN ... THEN` clause (KL-9) — severing the header's `target`/`src` aliases
from the `ON`/`UPDATE SET`/`INSERT` clauses that use them. A fix symmetric to
KL-9's (suppressing that split too) was prototyped and does resolve those
columns, but merging the two statement chunks also merges their table count
for the single-table unqualified-column fallback, which then stops resolving
the derived table's own unqualified `SELECT`-list columns — trading one
resolved column for another rather than a clean win. Pinned instead of
forced; see the `STMT_SPLIT` comment in `main.py`.

KL-2 through KL-7b and KL-15 remain documented, honest edge cases — see the
README table for what each one is and why it hasn't been fixed yet.
