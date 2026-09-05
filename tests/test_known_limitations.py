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
    CountryInfo CTE sources FROM PartyRef (another CTE) which sources FROM
    dbo.PartyCompany. A column referenced via the CountryInfo alias, renamed
    at every hop, should ultimately trace back to dbo.PartyCompany's real
    column -- it doesn't; it's silently dropped instead.

    Rewritten while fixing #16/#17 (KL-7/KL-7b): the original repro named its
    own CTE "Country" while ALSO directly joining a real dbo.Country inside
    that CTE's body. Fixing KL-7/KL-7b (which recovers dbo.Country from that
    exact collision) made this test XPASS -- but only because the asserted
    column landed on dbo.Country via that CTE-body's own local JOIN alias,
    completely independent of any multi-hop chain logic. Confirmed by testing
    a clean 2-hop chain with no local-JOIN shortcut: genuine multi-hop alias
    resolution still doesn't work. This version has no name collision and no
    local qualified/unqualified shortcut for the chased column -- the PartyRef
    JOIN exists only to disable the single-table unqualified-column fallback,
    which would otherwise mask the real gap the same way. The only column it
    contributes (PARTYID, from the JOIN's own ON-clause) is deliberately
    irrelevant to what's being chased.

    Root cause (see main.py, the qualified-columns loop): when a CTE's output
    alias is itself a passthrough of ANOTHER CTE (mapped_table is None), the
    code resolves the target table via `cte_src[source_cte]` directly --
    exactly one hop -- instead of `resolve_cte(source_cte, cte_src, cte_names)`,
    which already recurses through multiple hops (and IS used elsewhere, e.g.
    for a direct table alias like `FROM CountryInfo ctry`). That one-hop-only
    lookup returns another CTE's bare name, which is never in `physical`, so
    the reference is silently declined instead of chased further.
    """
    sql = """
    ;WITH PartyRef AS (
        SELECT CountryOfIncorporationId AS Hop1Col
        FROM dbo.PartyCompany pc
        JOIN dbo.PartyStatus ps ON ps.PartyId = pc.PartyId
    ),
    CountryInfo AS (SELECT Hop1Col AS Hop2Col FROM PartyRef)
    SELECT ctry.Hop2Col FROM CountryInfo ctry
    """
    physical, _ = parse_sp(sql)
    assert "COUNTRYOFINCORPORATIONID" in cols_of(physical, "DBO.PARTYCOMPANY"), \
        "ctry.Hop2Col should chain through CountryInfo -> PartyRef to dbo.PartyCompany"


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


