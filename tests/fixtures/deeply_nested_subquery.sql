/*
 * Fixture: subquery nested 3 levels deep inside a FROM clause, no CTE at all.
 *
 * FICTIONAL. Invented for this test suite. Any resemblance to a real schema is
 * coincidental -- see tests/fixtures/README.md before adding fixtures.
 *
 * Exercises: FROM (SELECT ... FROM (SELECT ... FROM (SELECT ... FROM
 * dbo.Party) ) ) -- three levels of derived-table nesting. Regex-based
 * statement splitting has no concept of nesting depth, so this probes
 * whether the innermost physical table and its real columns still resolve
 * correctly, and whether the outer wrapper aliases ever get misattributed.
 */
CREATE PROCEDURE dbo.usp_DeepNestedReport AS
BEGIN
    SELECT outer3.PartyId, outer3.PartyName
    FROM (
        SELECT outer2.PartyId, outer2.PartyName
        FROM (
            SELECT outer1.PartyId, outer1.PartyName
            FROM (
                SELECT p.PartyId, p.PartyName
                FROM dbo.Party p
                WHERE p.IsActive = 1
            ) outer1
        ) outer2
    ) outer3;
END
