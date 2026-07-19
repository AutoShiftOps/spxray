/*
 * Fixture: recursive CTE -- anchor member UNION ALL a self-referencing
 * recursive member.
 *
 * FICTIONAL. Invented for this test suite. Any resemblance to a real schema is
 * coincidental -- see tests/fixtures/README.md before adding fixtures.
 *
 * Exercises: a CTE that references ITSELF inside its own body via UNION ALL
 * (T-SQL doesn't require the RECURSIVE keyword). Checks the self-reference is
 * never mistaken for a distinct physical table, resolve_cte doesn't loop
 * forever, and a value computed only inside the CTE (Depth) is never
 * mis-attributed to the underlying physical table.
 */
CREATE PROCEDURE hr.usp_OrgChain @RootEmployeeId INT AS
BEGIN
    ;WITH OrgChain AS (
        SELECT e.EmployeeId, e.ManagerId, e.EmployeeName, 0 AS Depth
        FROM hr.Employee e
        WHERE e.EmployeeId = @RootEmployeeId

        UNION ALL

        SELECT e.EmployeeId, e.ManagerId, e.EmployeeName, oc.Depth + 1
        FROM hr.Employee e
        INNER JOIN OrgChain oc ON e.ManagerId = oc.EmployeeId
    )
    SELECT oc.EmployeeId, oc.EmployeeName, oc.Depth
    FROM OrgChain oc
    ORDER BY oc.Depth;
END
