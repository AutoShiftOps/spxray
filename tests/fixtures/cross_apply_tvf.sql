/*
 * Fixture: CROSS APPLY / OUTER APPLY -- a table-valued function and a
 * correlated subquery, neither reached via FROM/JOIN.
 *
 * FICTIONAL. Invented for this test suite. Any resemblance to a real schema is
 * coincidental -- see tests/fixtures/README.md before adding fixtures.
 *
 * Exercises: CROSS APPLY referencing a table-valued function (a function
 * call, not a schema object -- must never be registered as a physical
 * table), and OUTER APPLY referencing a correlated derived-table subquery
 * that DOES touch a real physical table.
 */
CREATE PROCEDURE sales.usp_OrderHistory @PartyId INT AS
BEGIN
    SELECT p.PartyId, p.PartyName, h.OrderId, h.OrderDate, latest.NoteText
    FROM dbo.Party p
    CROSS APPLY dbo.fn_GetRecentOrders(p.PartyId) h
    OUTER APPLY (
        SELECT TOP 1 n.NoteText
        FROM audit.PartyNotes n
        WHERE n.PartyId = p.PartyId
        ORDER BY n.CreatedDate DESC
    ) latest
    WHERE p.IsActive = 1;
END
