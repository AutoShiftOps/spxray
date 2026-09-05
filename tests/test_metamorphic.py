"""
LAYER — METAMORPHIC TESTS (#22)

Every other layer checks "does this ONE input produce the RIGHT output."
These check something different: "do two INPUTS THAT SHOULD MEAN THE SAME
THING produce the SAME output" -- catching bugs where the tool gives a
different answer to what is really the same query, without ever pinning
down what the "right" answer looks like in the first place.

Some of this already exists elsewhere (test_contracts.py::test_C1 checks
one input is stable across repeated runs; test_C4_cte_output_alias_...
checks one specific decoy-in-a-literal case) -- this file is the deliberate,
named layer for the general properties, per the four named in the issue:

  M1  Alias rename       -- renaming a table alias must not change which
                             real tables/columns get reported
  M2  Reformatting       -- whitespace/line-break/keyword-casing changes
                             must produce identical findings
  M3  String-literal decoy -- a fake FROM/table mention inside a string
                             literal must never create a phantom object
  M4  Statement reorder  -- reordering independent statements must not
                             change their (order-independent) results

Each compares two RELATED-BUT-DIFFERENT inputs to each other, not to a
fixed expected value -- that's what makes these "metamorphic" rather than
ordinary regression tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import parse_sp
from conftest import tables_of, cols_of


def _ops_snapshot(physical):
    """Tables + their ops + their columns -- NOT aliases (renaming those is
    exactly what M1 varies on purpose, so they must be excluded to compare
    the two runs on everything that SHOULD be identical)."""
    return {
        k: (tuple(sorted(v["ops"])), tuple(sorted(v["columns"])))
        for k, v in physical.items() if k != "__UNRESOLVED__"
    }


# ── M1: alias rename ─────────────────────────────────────────────────────────

def test_M1_renaming_aliases_does_not_change_tables_or_columns():
    original = """
    SELECT o.OrderID, c.CustomerName
    FROM sales.Orders o
    INNER JOIN sales.Customers c ON c.Id = o.CustomerId
    WHERE o.IsActive = 1
    """
    renamed = """
    SELECT zzz.OrderID, qqq.CustomerName
    FROM sales.Orders zzz
    INNER JOIN sales.Customers qqq ON qqq.Id = zzz.CustomerId
    WHERE zzz.IsActive = 1
    """
    phys_a, dyn_a = parse_sp(original)
    phys_b, dyn_b = parse_sp(renamed)
    assert _ops_snapshot(phys_a) == _ops_snapshot(phys_b), \
        "renaming aliases changed which tables/columns/ops were reported"
    assert dyn_a == dyn_b


def test_M1_renaming_a_cte_alias_does_not_change_resolution():
    original = """
    ;WITH PartyRef AS (SELECT PartyId, Name FROM dbo.Party)
    SELECT pr.Name FROM PartyRef pr
    """
    renamed = """
    ;WITH PartyRef AS (SELECT PartyId, Name FROM dbo.Party)
    SELECT ref9.Name FROM PartyRef ref9
    """
    phys_a, _ = parse_sp(original)
    phys_b, _ = parse_sp(renamed)
    assert _ops_snapshot(phys_a) == _ops_snapshot(phys_b)


# ── M2: reformatting ─────────────────────────────────────────────────────────

def test_M2_whitespace_and_linebreaks_do_not_change_result():
    compact = "SELECT o.Id, o.Total FROM sales.Orders o WHERE o.Total > 100;"
    spread = """
    SELECT
        o.Id  ,   o.Total
    FROM
        sales.Orders     o
    WHERE
        o.Total   >   100
    ;
    """
    phys_a, dyn_a = parse_sp(compact)
    phys_b, dyn_b = parse_sp(spread)
    assert _ops_snapshot(phys_a) == _ops_snapshot(phys_b), \
        "pure whitespace/line-break differences changed the result"
    assert dyn_a == dyn_b


def test_M2_keyword_casing_does_not_change_result():
    upper = "SELECT o.Id FROM sales.Orders o INNER JOIN sales.Customers c ON c.Id = o.CustomerId"
    lower = "select o.Id from sales.Orders o inner join sales.Customers c on c.Id = o.CustomerId"
    mixed = "Select o.Id From sales.Orders o Inner Join sales.Customers c On c.Id = o.CustomerId"
    phys_u, _ = parse_sp(upper)
    phys_l, _ = parse_sp(lower)
    phys_m, _ = parse_sp(mixed)
    snap_u, snap_l, snap_m = _ops_snapshot(phys_u), _ops_snapshot(phys_l), _ops_snapshot(phys_m)
    assert snap_u == snap_l == snap_m, \
        "SQL keyword casing (SELECT/select/Select) changed the result"


# ── M3: string-literal decoys ────────────────────────────────────────────────

def test_M3_decoy_table_mention_inside_string_literal_is_inert():
    clean = "SELECT a.Id FROM dbo.Alpha a WHERE a.Notes = 'no decoy here'"
    with_decoy = "SELECT a.Id FROM dbo.Alpha a WHERE a.Notes = 'ignore this: FROM dbo.PhantomDecoy JOIN dbo.AlsoFake'"
    phys_clean, _ = parse_sp(clean)
    phys_decoy, _ = parse_sp(with_decoy)
    assert tables_of(phys_clean) == tables_of(phys_decoy), \
        "a fake FROM/JOIN mention inside a string literal changed the table set"
    assert "DBO.PHANTOMDECOY" not in tables_of(phys_decoy)
    assert "DBO.ALSOFAKE" not in tables_of(phys_decoy)
    assert cols_of(phys_clean, "DBO.ALPHA") == cols_of(phys_decoy, "DBO.ALPHA")


def test_M3_decoy_column_mention_inside_string_literal_is_inert():
    clean = "UPDATE dbo.Beta SET Status = 'x' WHERE Id = 1"
    with_decoy = "UPDATE dbo.Beta SET Status = 'PhantomColumn = 1, AnotherFakeCol' WHERE Id = 1"
    phys_clean, _ = parse_sp(clean)
    phys_decoy, _ = parse_sp(with_decoy)
    assert cols_of(phys_clean, "DBO.BETA") == cols_of(phys_decoy, "DBO.BETA"), \
        "a decoy column-like string inside a literal changed resolved columns"


# ── M4: statement reordering ─────────────────────────────────────────────────

def test_M4_reordering_independent_statements_does_not_change_result():
    forward = """
    SELECT a.Id FROM dbo.Alpha a;
    SELECT b.Id FROM dbo.Bravo b;
    """
    reversed_ = """
    SELECT b.Id FROM dbo.Bravo b;
    SELECT a.Id FROM dbo.Alpha a;
    """
    phys_f, dyn_f = parse_sp(forward)
    phys_r, dyn_r = parse_sp(reversed_)
    assert _ops_snapshot(phys_f) == _ops_snapshot(phys_r), \
        "reordering two independent statements changed the combined result"
    assert dyn_f == dyn_r


def test_M4_reordering_three_independent_statements_does_not_change_result():
    a = "SELECT a.Id FROM dbo.Alpha a;"
    b = "UPDATE dbo.Bravo SET Flag = 1 WHERE Id = 1;"
    c = "DELETE FROM dbo.Charlie WHERE Id = 1;"
    orderings = [a + b + c, c + a + b, b + c + a]
    snapshots = [_ops_snapshot(parse_sp(sql)[0]) for sql in orderings]
    assert snapshots[0] == snapshots[1] == snapshots[2], \
        "reordering three independent statements changed the combined result"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
