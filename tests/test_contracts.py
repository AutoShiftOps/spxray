"""
LAYER 1 — CONTRACT TESTS

These encode the product's non-negotiable promises. If one of these fails, the
tool is lying to its users. Never delete a test here; never weaken an assertion
here to make a feature pass. If a contract genuinely must change, that is a
major version bump and a README change, discussed in an issue first.

Contracts:
  C1  Determinism        — same input always yields identical output
  C2  Physical-only      — temp tables and CTE names never appear as tables
  C3  No silent drops    — bad bytes never truncate a file
  C4  No guessing        — ambiguous columns are unresolved, never invented
  C5  Dynamic SQL honesty— EXEC/sp_executesql is always flagged
  C6  No AI in parsing   — extraction path makes zero network calls
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import parse_sp, read_bytes_safe
from conftest import sql_fixture, tables_of, cols_of


# ── C1: Determinism ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("fixture", [
    "multi_cte_report.sql",
    "crud_and_dynamic.sql",
    "alias_collision.sql",
    "postgres_proc.sql",
    "deeply_nested_subquery.sql",
    "cross_apply_tvf.sql",
    "recursive_cte.sql",
    "merge_output_clause.sql",
    "cte_table_collision_variant.sql",
    "utf16_bom.sql",
])
def test_C1_parsing_is_deterministic(fixture):
    """
    Five identical runs must produce byte-identical structures.

    Deliberately includes fixtures that expose known bugs (KL-7b..KL-11):
    determinism is orthogonal to correctness -- a bug should at least be a
    STABLE, reproducible bug, not a source of flakiness on top of being wrong.
    This is not a golden/correctness check (see test_golden.py).
    """
    sql = sql_fixture(fixture)
    runs = []
    for _ in range(5):
        physical, dynamic = parse_sp(sql)
        snapshot = sorted(
            (k, tuple(sorted(v["ops"])), tuple(sorted(v["columns"])))
            for k, v in physical.items()
        )
        runs.append((snapshot, dynamic))
    assert all(r == runs[0] for r in runs), f"{fixture} produced non-deterministic output"


# ── C2: Physical objects only ─────────────────────────────────────────────────

def test_C2_temp_tables_never_reported():
    physical, _ = parse_sp(sql_fixture("crud_and_dynamic.sql"))
    for t in tables_of(physical):
        assert not t.lstrip("[").startswith("#"), f"temp table leaked: {t}"


def test_C2_cte_names_never_reported_as_tables():
    physical, _ = parse_sp(sql_fixture("multi_cte_report.sql"))
    cte_names = {"LEDETAILS", "LEI", "COUNTRY", "REGIONRISKDETAILS",
                 "GROUPRISKRATING", "PRODUCTS"}
    for t in tables_of(physical):
        base = t.split(".")[-1]
        assert base not in cte_names, f"CTE name leaked as table: {t}"


def test_C2_variable_tables_never_reported():
    physical, _ = parse_sp("SELECT x.Id FROM @TableVar x")
    assert not any("@" in t for t in tables_of(physical))


# ── C3: No silent content loss ────────────────────────────────────────────────

def test_C3_bad_bytes_never_truncate_file():
    """The classic SSMS bug: 0x95/0x96 in a comment killed everything after it."""
    raw = (
        b"SELECT a.Id FROM dbo.TableAlpha a;\n"
        b"-- smart quote \x92 en-dash \x96 bullet \x95 accent \xe9\n"
        b"SELECT b.Id FROM dbo.TableBravo b;\n"
        b"-- more junk \x93\x94\n"
        b"SELECT c.Id FROM dbo.TableCharlie c;\n"
    )
    physical, _ = parse_sp(read_bytes_safe(raw))
    found = tables_of(physical)
    for expected in ("DBO.TABLEALPHA", "DBO.TABLEBRAVO", "DBO.TABLECHARLIE"):
        assert expected in found, f"content after bad byte was dropped: missing {expected}"


def test_C3_decoder_preserves_byte_count():
    raw = b"SELECT 1 -- caf\xe9 \x96 test"
    text = read_bytes_safe(raw)
    assert len(text) == len(raw), "decoder changed character count"


def test_C3_utf16_file_never_returns_empty_success():
    """
    A UTF-16LE-with-BOM file (a real "Save As" option in SSMS) must either be
    correctly decoded and parsed, or raise a clear error -- it must NEVER
    silently succeed with an empty report. Before this fix (KL-11), utf-8
    decoding of UTF-16 bytes didn't raise: most ASCII-range UTF-16LE bytes
    are individually valid UTF-8, so it silently "succeeded" into
    NUL-interleaved garbage that then failed every parser regex, returning a
    confident-looking empty result -- indistinguishable from "this file
    genuinely has no tables in it".
    """
    raw = "SELECT e.Id FROM hr.Employee e".encode("utf-16")
    try:
        text = read_bytes_safe(raw)
    except Exception:
        return  # a clear, visible error is an acceptable outcome too
    physical, _ = parse_sp(text)
    assert tables_of(physical), \
        "UTF-16 content was silently lost -- empty success, the one banned outcome"


# ── C4: Never invent, never guess ─────────────────────────────────────────────

def test_C4_ambiguous_columns_are_not_attributed():
    """Unqualified col in a multi-table SELECT must not be assigned to a table."""
    sql = """
    SELECT SomeAmbiguousColumn
    FROM dbo.TableOne t1
    INNER JOIN dbo.TableTwo t2 ON t2.Id = t1.Id
    """
    physical, _ = parse_sp(sql)
    for key in tables_of(physical):
        assert "SOMEAMBIGUOUSCOLUMN" not in cols_of(physical, key), \
            f"guessed ambiguous column onto {key}"


def test_C4_no_columns_invented_from_nothing():
    sql = "SELECT * FROM dbo.Wildcard w"
    physical, _ = parse_sp(sql)
    assert "DBO.WILDCARD" in tables_of(physical)
    assert cols_of(physical, "DBO.WILDCARD") == set(), "invented columns for SELECT *"


def test_C4_keywords_never_reported_as_columns():
    physical, _ = parse_sp(sql_fixture("multi_cte_report.sql"))
    banned = {"SELECT", "FROM", "WHERE", "INNER", "JOIN", "LEFT", "ORDER", "DISTINCT"}
    for key in tables_of(physical):
        leaked = cols_of(physical, key) & banned
        assert not leaked, f"SQL keywords reported as columns on {key}: {leaked}"


def test_C4_cte_output_alias_translation_does_not_reopen_the_literal_hole():
    """
    KL-1's fix (extract_cte_output_map, main.py) reads a SECOND copy of the
    SQL that skips mask_string_literals -- needed to recover output-alias text
    like `AS 'Party ID'`, which the masked pipeline nulls out by design. That
    second pass must never be allowed to leak a table name sitting inside an
    ordinary string literal back into the report; it exists only to resolve
    alias->source-column bindings, never to detect tables.

    This CTE body carries both a real output alias (Id AS 'Foo') and a data
    literal containing a fake FROM clause in the SAME WHERE clause the
    alias-preserving pass also parses (to resolve JOIN-alias qualifiers) --
    the two must not interact.
    """
    sql = (
        ";WITH X AS ("
        "SELECT Id AS 'Foo' FROM dbo.Real WHERE Note='x FROM dbo.Phantom'"
        ") SELECT X.[Foo] FROM X"
    )
    physical, _ = parse_sp(sql)
    assert "DBO.PHANTOM" not in tables_of(physical), \
        "string literal content invented a phantom table"
    assert "ID" in cols_of(physical, "DBO.REAL"), \
        "the real source column must still be reported"
    assert "FOO" not in cols_of(physical, "DBO.REAL") and "Foo" not in cols_of(physical, "DBO.REAL"), \
        "the output alias must not be reported as a physical column"


# ── C5: Dynamic SQL honesty ───────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "EXEC('SELECT 1')",
    "EXECUTE('SELECT 1')",
    "EXEC sp_executesql @q",
    "DECLARE @s NVARCHAR(MAX); EXEC sp_executesql @s",
])
def test_C5_dynamic_sql_always_flagged(sql):
    _, dynamic = parse_sp(sql)
    assert dynamic, f"failed to flag dynamic SQL: {sql}"


def test_C5_static_sql_not_falsely_flagged():
    _, dynamic = parse_sp("SELECT c.Id FROM dbo.Customers c")
    assert not dynamic


# ── C6: Extraction path is offline ────────────────────────────────────────────

def test_C6_parsing_makes_no_network_calls(monkeypatch):
    """The parser must never phone home. AI is a separate, opt-in endpoint."""
    import socket

    def boom(*args, **kwargs):
        raise AssertionError("parser attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", boom)
    physical, _ = parse_sp(sql_fixture("multi_cte_report.sql"))
    assert tables_of(physical), "parser produced no output"
