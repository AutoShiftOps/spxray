"""
LAYER 3 — KNOWN LIMITATIONS (xfail)

Every test here documents a real, reproducible defect we have chosen not to fix
yet. They are marked `xfail(strict=True)`, which means:

  - While the defect exists, the test "fails as expected" and CI stays green.
  - The DAY SOMEONE FIXES IT, the test XPASSes and CI turns RED — forcing the
    fixer to promote it to a real assertion in test_regressions.py.

This is how we keep an honest, machine-checked list of what the tool gets wrong.
Nothing rots silently. The README's "Honest limitations" table must stay in sync
with this file.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import parse_sp
from conftest import cols_of, tables_of


@pytest.mark.xfail(strict=True, reason="KL-3: multi-hop CTE chains do not fully resolve")
def test_KL3_multi_hop_cte_chain_resolves():
    """
    Country CTE sources FROM PartyRef (another CTE) which sources FROM dbo.PartyCompany.
    Columns referenced via the Country alias should reach dbo.PartyCompany.
    """
    sql = """
    ;WITH PartyRef AS (SELECT PartyId, CountryOfIncorporationId FROM dbo.PartyCompany),
    Country AS (SELECT c.Id, c.ShortName FROM PartyRef INNER JOIN dbo.Country c ON c.id = PartyRef.CountryOfIncorporationId)
    SELECT ctry.ShortName FROM Country ctry
    """
    physical, _ = parse_sp(sql)
    assert "SHORTNAME" in cols_of(physical, "DBO.COUNTRY")


@pytest.mark.xfail(strict=True, reason="KL-4: dynamic SQL table names are unknowable statically")
def test_KL4_dynamic_sql_tables_extracted():
    """
    Will never pass without executing the SQL. Kept as a permanent marker that
    this is a deliberate design boundary, not an oversight. If this ever
    XPASSes, someone added runtime execution — that is a security review.
    """
    sql = "DECLARE @s NVARCHAR(MAX) = N'SELECT * FROM dbo.SecretTable'; EXEC sp_executesql @s;"
    physical, _ = parse_sp(sql)
    assert "DBO.SECRETTABLE" in tables_of(physical)


@pytest.mark.xfail(strict=True, reason="KL-5: operand columns inside an expression-derived CTE output are not surfaced")
def test_KL5_expression_derived_cte_output_not_resolved():
    """
    `SELECT CustomerId, SUM(Amount) AS 'Total' FROM dbo.Orders` inside a CTE
    means 'Total' is a computed EXPRESSION, not a passthrough of a real
    column -- there is no single source column to bind it to. We correctly
    refuse to invent a physical column called 'Total' on dbo.Orders (that
    part already passes -- never-invent holds).

    What we do NOT yet do is look inside the expression to note that 'Amount'
    is a real column being read. That would need actual expression parsing,
    not a simple AS-binding regex -- out of scope for the KL-1 fix. Documented
    here as a known gap: if 'Total' is ever attributed to dbo.Orders, that is
    a never-invent regression; if 'AMOUNT' starts appearing, someone added
    operand extraction and this should be promoted to a real feature test.
    """
    sql = """
    ;WITH OrderTotals AS (
        SELECT CustomerId, SUM(Amount) AS 'Total' FROM dbo.Orders GROUP BY CustomerId
    )
    SELECT OT.[Total] FROM OrderTotals OT
    """
    physical, _ = parse_sp(sql)
    cols = cols_of(physical, "DBO.ORDERS")
    assert "Total" not in cols and "TOTAL" not in cols, \
        "must never invent a physical column from an expression alias"
    assert "AMOUNT" in cols, \
        "the real operand column referenced inside SUM() should be surfaced too"


@pytest.mark.xfail(strict=True, reason="KL-7: a physical table is dropped entirely when its base name collides with a same-named CTE")
def test_KL7_physical_table_dropped_when_name_collides_with_cte():
    """
    `WITH Country AS (SELECT c.Id FROM dbo.Country c) SELECT * FROM Country`
    -- dbo.Country vanishes from the report completely. The table-registration
    exclusion check in parse_sp (main.py) is:

        if (base in SKIP_WORDS or base in cte_names or full in cte_names ...)

    It exists to satisfy C2 (a CTE's own name must never be reported as if it
    were a physical table). But it compares by BARE base name only, so a CTE
    named "Country" makes `base in cte_names` true for EVERY table literally
    named Country too, in ANY schema -- dbo.Country, sales.Country, etc. all
    get excluded, not just the CTE itself.

    This is the most serious class of bug this tool can produce: KL-1/KL-6 are
    wrong or missing COLUMNS, recoverable by re-reading the procedure. This is
    a physical table a migration plan needs to know about not appearing in the
    report AT ALL, with no flag, warning, or indication that anything was
    dropped -- indistinguishable from "this procedure never touches Country".
    First observed as a side effect while building the multi_cte_report.sql
    fixture for the KL-1 fix; not something that fixture's own goldens can
    catch since dbo.Country was never expected to appear there either.
    """
    sql = ";WITH Country AS (SELECT c.Id FROM dbo.Country c) SELECT * FROM Country"
    physical, _ = parse_sp(sql)
    assert "DBO.COUNTRY" in tables_of(physical), \
        "a same-named CTE caused the physical table to be dropped entirely"


@pytest.mark.xfail(strict=True, reason="KL-7: confirmed to generalize -- an unrelated table sharing a CTE's name is dropped anywhere in the procedure, not just references reachable through the colliding CTE")
def test_KL7b_collision_drops_unrelated_same_named_table_anywhere_in_procedure():
    """
    A CTE named "Product", built from an entirely different table
    (dbo.CaseFile), coexists with a COMPLETELY SEPARATE statement that
    directly queries the real dbo.Product -- never through the CTE at all.
    dbo.Product still vanishes. Confirms KL-7's exclusion check
    (`base in cte_names`) is a blunt, procedure-wide set-membership test with
    no locality: it drops every table sharing that bare name anywhere in the
    procedure, not just references reachable through the colliding CTE.

    First observed via tests/fixtures/cte_table_collision_variant.sql.
    """
    sql = """
    ;WITH Product AS (SELECT c.CaseId FROM dbo.CaseFile c)
    SELECT p.CaseId FROM Product p;

    SELECT sp.Id FROM dbo.Product sp;
    """
    physical, _ = parse_sp(sql)
    assert "DBO.PRODUCT" in tables_of(physical), \
        "an unrelated table was dropped just for sharing a name with a CTE"


@pytest.mark.xfail(strict=True, reason="KL-15: a MERGE's USING (subquery) clause severs the header's target/src aliases from the ON/UPDATE SET/INSERT clauses that use them")
def test_KL15_merge_using_subquery_does_not_sever_target_alias():
    """
    STMT_SPLIT treats any bare SELECT keyword as a new top-level statement
    boundary, with one exception carved out for KL-9 (a MERGE's own
    `WHEN ... THEN` sub-clause). A MERGE's `USING (SELECT ...) AS src`
    derived table has its OWN SELECT keyword, which is not that exception --
    it still splits there, severing "MERGE tbl AS target USING (" from
    "SELECT ... FROM src) AS src ON target.Col = ... WHEN MATCHED THEN
    UPDATE SET target.Col2 = ...". The second chunk has no idea "target" is
    an alias for tbl at all, so every target.-qualified column (and the
    MERGE's own WHEN NOT MATCHED THEN INSERT (...) column list, see the
    INSERT-target-column-list fix) goes unresolved -- even though KL-12 now
    makes the alias itself valid.

    Found and reproduced while fixing KL-12/KL-13: suppressing the split
    (making it symmetric with KL-9's fix) does resolve target./src. columns,
    but merging the two chunks also merges their table counts for the
    single-table unqualified-column fallback -- the derived table's own
    unqualified SELECT-list columns (e.g. a plain `WarehouseID` with no
    alias) then fail the "exactly one table in this statement" heuristic
    and stop resolving, trading one resolved column for another rather than
    a clean win. Pinned rather than forced; see main.py's STMT_SPLIT comment.
    """
    sql = """
    MERGE dbo.Party AS target
    USING (SELECT Id, Name FROM dbo.PartyStaging) AS src
    ON target.Id = src.Id
    WHEN MATCHED THEN UPDATE SET target.Name = src.Name;
    """
    physical, _ = parse_sp(sql)
    assert {"ID", "NAME"} <= cols_of(physical, "DBO.PARTY"), \
        "target.-qualified columns should resolve now that KL-12 allows the alias"


