/*
 * Fixture: a CTE named identically to a DIFFERENT physical table than KL-7's
 * own case, to test whether that collision bug generalizes.
 *
 * FICTIONAL. Invented for this test suite. Any resemblance to a real schema is
 * coincidental -- see tests/fixtures/README.md before adding fixtures.
 *
 * Exercises: a CTE named "Product" built from sales.CaseFile -- deliberately
 * unrelated to sales.Product -- while a COMPLETELY SEPARATE statement in the
 * same procedure directly queries the real sales.Product table, never
 * through the CTE at all. Checks whether naming a CTE "Product" drops every
 * reference to any table literally named Product anywhere in the procedure,
 * even ones with no relationship to the colliding CTE.
 */
CREATE PROCEDURE sales.usp_ProductAndCaseSummary AS
BEGIN
    ;WITH Product AS (
        SELECT c.CaseId, c.CaseStatus
        FROM sales.CaseFile c
        WHERE c.CaseStatus = 'Open'
    )
    SELECT p.CaseId FROM Product p;

    SELECT sp.ProductId, sp.ProductName
    FROM sales.Product sp
    WHERE sp.IsDiscontinued = 0;
END
