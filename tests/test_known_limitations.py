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


@pytest.mark.xfail(strict=True, reason="KL-2: display casing is inconsistent between bracketed and plain identifiers")
def test_KL2_identifier_casing_is_consistent():
    """
    `dbo.Alpha` renders as ALPHA, `[dbo].[Bravo]` renders as Bravo. Cosmetic,
    but it looks sloppy in an enterprise report and makes Excel sorting odd.
    """
    sql = "SELECT a.Id FROM dbo.Alpha a INNER JOIN [dbo].[Bravo] b ON b.Id = a.Id"
    physical, _ = parse_sp(sql)
    bases = [v["base"] for v in physical.values()]
    assert all(b.isupper() for b in bases) or all(not b.isupper() for b in bases), \
        f"inconsistent casing: {bases}"


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


@pytest.mark.xfail(strict=True, reason="KL-6: a column referenced through a CTE alias is attributed even when the CTE never outputs a column by that name")
def test_KL6_nonexistent_cte_output_column_not_attributed():
    """
    `WITH X AS (SELECT Id, Name FROM dbo.Real) SELECT X.Missing FROM X` -- X
    only ever outputs Id and Name. 'Missing' is neither a passthrough column
    nor an aliased output; it does not exist on X at all. We still attribute
    'MISSING' to dbo.Real, because the qualified-column loop only checks
    "does prefix resolve to a physical table", never "does the CTE actually
    expose a column by this name".

    A sibling of KL-1 (see extract_cte_output_map, main.py): KL-1 is a column
    the CTE RENAMED being reported under the wrong name; this is a column the
    CTE never claimed at all being reported as if it were real. Fixing it
    needs the inverse of extract_cte_output_map -- a per-CTE allow-list of
    every column the CTE actually outputs (passthrough AND aliased), checked
    before attribution, not just an alias->source translation table.

    First observed in tests/fixtures/multi_cte_report.sql: the outer query
    joins `ON PD.[Party ID] = P.PID`, but the Products CTE never selects
    anything named PID (it outputs id, caseid, 'Product Type') -- SALES.PRODUCT
    still reports a PID column after the KL-1 fix, for exactly this reason.
    """
    sql = """
    ;WITH X AS (SELECT Id, Name FROM dbo.Real)
    SELECT X.Missing FROM X
    """
    physical, _ = parse_sp(sql)
    assert "MISSING" not in cols_of(physical, "DBO.REAL"), \
        "attributed a column the CTE never actually outputs"


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


@pytest.mark.xfail(strict=True, reason="KL-8: the single-table unqualified-SELECT fallback strips ANY alias prefix, misattributing columns from an unrelated source")
def test_KL8_unqualified_select_fallback_misattributes_other_alias_columns():
    """
    `SELECT p.Id, h.OrderId FROM dbo.Party p CROSS APPLY dbo.fn_Recent(p.Id) h`
    -- CROSS APPLY isn't a recognized FROM/JOIN keyword, so stmt_tables ends
    up with exactly ONE table (dbo.Party), and the "unqualified SELECT --
    single table only" fallback in parse_sp fires. That fallback tokenizes
    the whole SELECT list and does `token.split('.')[-1]` on every token to
    strip schema-qualification -- but this ALSO strips a genuine alias prefix
    like `h.`, so 'h.OrderId' becomes bare 'OrderId' and gets attributed to
    dbo.Party even though it has nothing to do with that table. The fallback
    has no idea some of these tokens were already (safely) left unresolved by
    the qualified-columns pass moments earlier.

    First observed via tests/fixtures/cross_apply_tvf.sql. The exact same
    code path is hit by tests/fixtures/recursive_cte.sql: a self-referencing
    recursive CTE's `oc.Depth` (a value computed only inside the CTE, via
    `0 AS Depth` in the anchor member) gets attributed to hr.Employee, a
    table that has no Depth column at all.

    Same defect CLASS as KL-1 (fixed) and KL-6, though a different code path:
    a column gets attributed on the strength of ONE fallible signal, without
    cross-checking a SEPARATE signal already computed elsewhere in the same
    pass that says the attribution is wrong.
      - KL-1: the alias resolved to a physical table, full stop -- without
        checking the CTE's own output-alias map (extract_cte_output_map) for
        whether that name was a renamed column.
      - KL-6: same map, but for whether the name was ever output AT ALL.
      - KL-8: the *qualified*-columns pass, moments earlier in the exact same
        statement, already (correctly) declined to resolve this reference --
        the *unqualified* single-table fallback reprocesses the same text and
        overrides that correct refusal, unaware it happened.
    A fix that makes the single-table fallback skip tokens the qualified pass
    already looked at (rather than re-tokenizing the same text blind) would
    close KL-8 and hand KL-6 a natural place to plug into as well.
    """
    sql = "SELECT p.Id, h.OrderId FROM dbo.Party p CROSS APPLY dbo.fn_Recent(p.Id) h"
    physical, _ = parse_sp(sql)
    assert "ORDERID" not in cols_of(physical, "DBO.PARTY"), \
        "a column from an unrelated alias (h) was attributed to dbo.Party"


@pytest.mark.xfail(strict=True, reason="KL-9: MERGE target and USING source aliases are never captured, so their columns silently fail to resolve")
def test_KL9_merge_target_and_using_source_aliases_not_resolved():
    """
    `MERGE dbo.Party AS tgt USING dbo.PartyStaging AS src ON tgt.Id = src.Id
    WHEN MATCHED THEN UPDATE SET tgt.Name = src.Name` -- both alias->table
    bindings should be captured, so tgt.Id/tgt.Name attribute to dbo.Party
    and src.Id/src.Name attribute to dbo.PartyStaging. Neither does.

    Two separate causes in build_alias_map's main pattern:
      r'(?:FROM|JOIN|UPDATE|MERGE\\s+(?:INTO\\s+)?)\\s+((?:[\\w]+\\.)*[\\w]+)...'
    (1) The MERGE branch is `MERGE\\s+(?:INTO\\s+)?` immediately followed by
        ANOTHER required `\\s+` outside the group. Plain "MERGE table" (one
        space, no INTO) needs the inner `\\s+` to consume that one space,
        leaving nothing for the outer mandatory `\\s+` -- the whole pattern
        never matches for ordinary single-spaced MERGE syntax.
    (2) USING is not in the alias-detection keyword list at all
        (FROM|JOIN|UPDATE|MERGE only), so 'src' is never bound regardless.

    First observed via tests/fixtures/merge_output_clause.sql, where
    risk.RatingDetails and refdata.RatingFeed are both correctly registered
    as touched (TABLE_OP_PATTERNS does include MERGE and USING) but end up
    with zero columns each.
    """
    sql = """
    MERGE dbo.Party AS tgt
    USING dbo.PartyStaging AS src
    ON tgt.Id = src.Id
    WHEN MATCHED THEN UPDATE SET tgt.Name = src.Name;
    """
    physical, _ = parse_sp(sql)
    assert {"ID", "NAME"} <= cols_of(physical, "DBO.PARTY"), \
        f"MERGE target alias (tgt) columns not resolved: {cols_of(physical, 'DBO.PARTY')}"
    assert {"ID", "NAME"} <= cols_of(physical, "DBO.PARTYSTAGING"), \
        f"MERGE USING alias (src) columns not resolved: {cols_of(physical, 'DBO.PARTYSTAGING')}"


@pytest.mark.xfail(strict=True, reason="KL-10: OUTPUT ... INTO's target table is not recognized -- a written-to table can be silently missing from the report")
def test_KL10_output_into_target_table_not_recognized():
    """
    `... OUTPUT inserted.Id, inserted.Name INTO audit.ChangeLog (Id, Name);`
    -- audit.ChangeLog is genuinely written to (every OUTPUT INTO writes
    rows), but none of TABLE_OP_PATTERNS recognizes "OUTPUT ... INTO" as a
    table reference, so it never appears in the report at all. Same severity
    class as KL-7: a physical table a migration plan needs to know about,
    silently absent, with no flag or warning.

    First observed via tests/fixtures/merge_output_clause.sql, where
    audit.RatingSyncLog (the MERGE's OUTPUT INTO target) never appears even
    though the MERGE and USING tables are both correctly registered.
    """
    sql = """
    UPDATE dbo.Party SET Name = 'x'
    OUTPUT inserted.Id, inserted.Name INTO audit.ChangeLog (Id, Name);
    """
    physical, _ = parse_sp(sql)
    assert "AUDIT.CHANGELOG" in tables_of(physical), \
        "OUTPUT INTO target table is missing from the report"
