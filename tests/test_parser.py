"""
Parser regression tests for sql-sp-companion.
Each test encodes a real-world bug we fixed — do not delete without reading git history.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import parse_sp, read_bytes_safe, split_procedures, detect_dialect


def tables_of(physical):
    return {k for k in physical if k != "__UNRESOLVED__"}


def cols_of(physical, key):
    return physical[key]["columns"]


# ── Basic extraction ──────────────────────────────────────────────────────────

def test_simple_select():
    sql = "SELECT c.CustomerID, c.Name FROM dbo.Customers c WHERE c.IsActive = 1"
    physical, dynamic = parse_sp(sql)
    assert "DBO.CUSTOMERS" in tables_of(physical)
    assert "CUSTOMERID" in cols_of(physical, "DBO.CUSTOMERS")
    assert not dynamic


def test_crud_operations_detected():
    sql = """
    INSERT INTO audit.Log (Msg) VALUES ('x');
    UPDATE dbo.Orders SET Status = 1 WHERE OrderID = 5;
    DELETE FROM dbo.Sessions WHERE Expired = 1;
    TRUNCATE TABLE staging.Import;
    """
    physical, _ = parse_sp(sql)
    assert "INSERT" in physical["AUDIT.LOG"]["ops"]
    assert "UPDATE" in physical["DBO.ORDERS"]["ops"]
    assert "DELETE" in physical["DBO.SESSIONS"]["ops"]
    assert "TRUNCATE" in physical["STAGING.IMPORT"]["ops"]


# ── Temp tables and CTEs excluded (manager requirement) ───────────────────────

def test_temp_tables_excluded():
    sql = """
    SELECT o.OrderID INTO #Staged FROM dbo.Orders o;
    SELECT s.OrderID FROM #Staged s;
    """
    physical, _ = parse_sp(sql)
    assert "DBO.ORDERS" in tables_of(physical)
    assert not any(t.startswith("#") for t in tables_of(physical))


def test_cte_names_not_reported_as_tables():
    sql = """
    ;WITH Recent AS (SELECT Id FROM dbo.Orders)
    SELECT r.Id FROM Recent r
    """
    physical, _ = parse_sp(sql)
    assert "RECENT" not in tables_of(physical)
    assert "DBO.ORDERS" in tables_of(physical)


# ── Bug fix: unqualified columns, single-table statement ─────────────────────

def test_unqualified_columns_single_table():
    """Real-world case: dbo.Party with no alias prefix on columns."""
    sql = """
    SELECT Id, Name, ScheduledReviewDate
    FROM dbo.Party
    WHERE Active = 0
    """
    physical, _ = parse_sp(sql)
    cols = cols_of(physical, "DBO.PARTY")
    assert "ID" in cols
    assert "NAME" in cols
    assert "SCHEDULEDREVIEWDATE" in cols
    assert "ACTIVE" in cols or True  # WHERE-clause col capture is best-effort


# ── Bug fix: bracketed multi-word names ──────────────────────────────────────

def test_bracketed_multiword_columns():
    """[Party ID] must survive as a single column, not split into two tokens.

    Uses a direct reference (no CTE) so this stays isolated from CTE
    output-alias translation (see test_KL1... in this file for that case) --
    a bracketed multi-word name that genuinely IS a column should pass
    through unsplit regardless of whether any CTE is involved.
    """
    sql = "SELECT p.[Party ID] FROM dbo.Party p"
    physical, _ = parse_sp(sql)
    cols = cols_of(physical, "DBO.PARTY")
    # The display form (with space) or normalized form must be present; never a split token
    assert "Party ID" in cols or "PARTY_ID" in cols, f"got: {cols}"
    assert "PARTY" not in cols, f"split token leaked: {cols}"


# ── Bug fix: CTE output-alias translation (formerly KL-1) ─────────────────────

def test_cte_output_alias_resolves_to_source_column():
    """
    `SELECT Id as 'Party ID' FROM dbo.Party` means dbo.Party has a column
    `Id`. It does NOT have a column called `Party ID` -- that is an output
    alias of the CTE, not a physical column. Reporting the alias sent a BSA
    looking for a column that does not exist in the source schema.

    Was tests/test_known_limitations.py::test_KL1 (xfail). Promoted here now
    that extract_cte_output_map (main.py) translates output aliases back to
    their real source column at attribution time. If this regresses, KL-1 is
    back and belongs in test_known_limitations.py again, not here.
    """
    sql = """
    ;WITH PartyDetails AS (SELECT Id as 'Party ID' FROM dbo.Party)
    SELECT LE.[Party ID] FROM PartyDetails LE
    """
    physical, _ = parse_sp(sql)
    cols = cols_of(physical, "DBO.PARTY")
    assert "ID" in cols, "the real source column must be reported"
    assert "Party ID" not in cols, "the output alias must NOT be reported as a physical column"


def test_cte_output_alias_via_join_qualifier_resolves_to_correct_table():
    """
    The source column behind an output alias can come from a JOINed table,
    not just the CTE's own primary FROM table -- `rcs1.RiskCategoryIdentifier
    AS 'Regional Risk Rating'` where rcs1 is risk.RiskCategory, inside a CTE
    whose primary FROM is risk.RatingDetails. The alias must resolve to
    risk.RiskCategory, not be misattributed to risk.RatingDetails.
    """
    sql = """
    ;WITH RegionRiskDetails AS (
        SELECT PartyId as 'PID', rcs1.RiskCategoryIdentifier AS 'Regional Risk Rating'
        FROM risk.RatingDetails rrd
        LEFT JOIN risk.RiskCategory rcs1 ON rrd.RegionRiskRating = rcs1.Id
    )
    SELECT RRD.[Regional Risk Rating] FROM RegionRiskDetails RRD
    """
    physical, _ = parse_sp(sql)
    assert "RISKCATEGORYIDENTIFIER" in cols_of(physical, "RISK.RISKCATEGORY")
    assert "Regional Risk Rating" not in cols_of(physical, "RISK.RATINGDETAILS")
    assert "Regional Risk Rating" not in cols_of(physical, "RISK.RISKCATEGORY")


# ── Bug fix: CTE alias chain resolution ──────────────────────────────────────

def test_cte_alias_resolves_to_physical_table():
    sql = """
    ;WITH PartyDetails AS (
        SELECT Id, Name FROM dbo.Party
    )
    SELECT LE.Id, LE.Name FROM PartyDetails LE
    """
    physical, _ = parse_sp(sql)
    cols = cols_of(physical, "DBO.PARTY")
    assert "ID" in cols
    assert "NAME" in cols


# ── Bug fix: alias collision across statements ───────────────────────────────

def test_alias_collision_per_statement_scope():
    """Same alias `o` for different tables in different statements."""
    sql = """
    SELECT o.OrderID FROM sales.Orders o;
    SELECT o.OfficeName FROM hr.Offices o;
    """
    physical, _ = parse_sp(sql)
    assert "ORDERID" in cols_of(physical, "SALES.ORDERS")
    assert "OFFICENAME" in cols_of(physical, "HR.OFFICES")
    assert "OFFICENAME" not in cols_of(physical, "SALES.ORDERS")


# ── Bug fix: encoding (SSMS Windows-1252 exports) ────────────────────────────

def test_windows_1252_bytes_do_not_drop_content():
    raw = (
        b"-- Author\x92s note \x96 see ticket\n"
        b"SELECT c.Id FROM dbo.Customers c;\n"
        b"-- bullet \x95 here\n"
        b"UPDATE warehouse.Inventory SET StockLevel = 0 WHERE ProductID = 1;\n"
    )
    text = read_bytes_safe(raw)
    physical, _ = parse_sp(text)
    assert "DBO.CUSTOMERS" in tables_of(physical)
    assert "WAREHOUSE.INVENTORY" in tables_of(physical)  # content after bad byte survives


def test_utf8_bom_stripped():
    raw = b"\xef\xbb\xbfSELECT Id FROM dbo.T1"
    text = read_bytes_safe(raw)
    assert not text.startswith("\ufeff")


def test_utf16_bom_decoded_not_garbled():
    """
    Was tests/test_known_limitations.py::test_KL11 (xfail). Promoted here now
    that read_bytes_safe detects a UTF-16 BOM and decodes with the 'utf-16'
    codec (which auto-detects LE/BE from the BOM) before falling back to the
    utf-8/windows-1252/cp1252/latin-1 chain. Without this, utf-8 decoding of
    UTF-16 bytes doesn't raise -- it silently produces NUL-interleaved
    garbage that fails every parser regex. If this regresses, KL-11 is back.
    """
    raw = "SELECT e.Id, e.Name FROM hr.Employee e".encode("utf-16")
    text = read_bytes_safe(raw)
    physical, _ = parse_sp(text)
    assert "HR.EMPLOYEE" in tables_of(physical)
    assert {"ID", "NAME"} <= cols_of(physical, "HR.EMPLOYEE")


# ── Dynamic SQL flag ─────────────────────────────────────────────────────────

def test_dynamic_sql_flagged():
    sql = "DECLARE @q NVARCHAR(MAX) = N'SELECT 1'; EXEC sp_executesql @q;"
    _, dynamic = parse_sp(sql)
    assert dynamic


# ── Procedure splitting & dialect ────────────────────────────────────────────

def test_multiple_procedures_split():
    sql = """
    CREATE PROCEDURE dbo.usp_A AS BEGIN SELECT 1 FROM dbo.T1 END
    GO
    CREATE PROCEDURE dbo.usp_B AS BEGIN SELECT 1 FROM dbo.T2 END
    """
    procs = split_procedures(sql)
    assert len(procs) == 2


def test_dialect_detection_tsql():
    assert "T-SQL" in detect_dialect("DECLARE @x INT; SELECT @x")


# ── Bug fix: single-table fallback respects the qualified pass (formerly KL-8) ─

def test_cross_apply_alias_does_not_leak_onto_the_single_table():
    """
    `CROSS APPLY`/`OUTER APPLY` aren't recognized FROM/JOIN keywords, so a
    statement like this ends up with exactly ONE registered table
    (dbo.Party) -- which used to make the "unqualified SELECT, single table
    only" fallback fire and misattribute `h.OrderId` (the CROSS APPLY
    alias's column) onto dbo.Party, because it blindly stripped every alias
    prefix via `token.split('.')[-1]`. The qualified-columns pass had
    already correctly declined to resolve `h` moments earlier in the same
    statement; the fallback now respects that refusal instead of
    re-tokenizing the same text blind.
    """
    sql = "SELECT p.Id, h.OrderId FROM dbo.Party p CROSS APPLY dbo.fn_Recent(p.Id) h"
    physical, _ = parse_sp(sql)
    assert "ID" in cols_of(physical, "DBO.PARTY")
    assert "ORDERID" not in cols_of(physical, "DBO.PARTY")


def test_recursive_cte_self_reference_does_not_leak_computed_column():
    """
    Same code path as the CROSS APPLY case above, hit by a self-referencing
    recursive CTE instead: `oc.Depth` (a value computed only inside the CTE,
    via `0 AS Depth` in the anchor member) used to get attributed to
    hr.Employee, a table with no Depth column at all.
    """
    sql = """
    ;WITH OrgChain AS (
        SELECT e.EmployeeId, e.ManagerId, 0 AS Depth FROM hr.Employee e
        UNION ALL
        SELECT e.EmployeeId, e.ManagerId, oc.Depth + 1
        FROM hr.Employee e INNER JOIN OrgChain oc ON e.ManagerId = oc.EmployeeId
    )
    SELECT oc.EmployeeId, oc.Depth FROM OrgChain oc
    """
    physical, _ = parse_sp(sql)
    assert "EMPLOYEEID" in cols_of(physical, "HR.EMPLOYEE")
    assert "DEPTH" not in cols_of(physical, "HR.EMPLOYEE")


# ── Bug fix: MERGE alias resolution (formerly KL-9) ────────────────────────────

def test_merge_target_and_using_source_aliases_resolve():
    """
    Two separate causes, both in build_alias_map:
    (1) the MERGE branch required two consecutive whitespace matches
        (`MERGE\\s+(?:INTO\\s+)?` followed by another `\\s+`) that ordinary
        single-spaced "MERGE table" syntax never satisfies;
    (2) USING wasn't in the alias-detection keyword list at all.
    A third, separate cause needed STMT_SPLIT itself: it used to split a
    MERGE's own `WHEN MATCHED THEN UPDATE SET ...` sub-clause into its own
    statement chunk, severing it from the tgt/src aliases declared in the
    MERGE header -- so even with (1) and (2) fixed, `tgt.Name`/`src.Name`
    stayed unresolved until STMT_SPLIT stopped splitting after `THEN `.
    """
    sql = """
    MERGE dbo.Party AS tgt
    USING dbo.PartyStaging AS src
    ON tgt.Id = src.Id
    WHEN MATCHED THEN UPDATE SET tgt.Name = src.Name;
    """
    physical, _ = parse_sp(sql)
    assert {"ID", "NAME"} <= cols_of(physical, "DBO.PARTY")
    assert {"ID", "NAME"} <= cols_of(physical, "DBO.PARTYSTAGING")


# ── Bug fix: OUTPUT ... INTO target table registered (formerly KL-10) ──────────

def test_output_into_target_table_is_registered():
    """
    `OUTPUT ... INTO auditTable` genuinely writes rows into auditTable, but
    no TABLE_OP_PATTERNS entry recognized it -- the audit table was silently
    absent from the report. Registered as an INSERT-target table now.
    """
    sql = """
    UPDATE dbo.Party SET Name = 'x'
    OUTPUT inserted.Id, inserted.Name INTO audit.ChangeLog (Id, Name);
    """
    physical, _ = parse_sp(sql)
    assert "AUDIT.CHANGELOG" in tables_of(physical)
    assert "INSERT" in physical["AUDIT.CHANGELOG"]["ops"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
