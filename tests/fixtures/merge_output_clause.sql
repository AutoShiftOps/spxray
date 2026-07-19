/*
 * Fixture: MERGE ... OUTPUT clause writing deltas to an audit table.
 *
 * FICTIONAL. Invented for this test suite. Any resemblance to a real schema is
 * coincidental -- see tests/fixtures/README.md before adding fixtures.
 *
 * Exercises: MERGE target/source, WHEN MATCHED/NOT MATCHED, and an
 * OUTPUT ... INTO clause writing the merge deltas into a THIRD table -- a
 * common T-SQL audit-logging pattern. OUTPUT INTO isn't a JOIN/FROM keyword,
 * so this checks whether that third table is recognized at all.
 */
CREATE PROCEDURE risk.usp_SyncRatingDetails AS
BEGIN
    MERGE risk.RatingDetails AS tgt
    USING refdata.RatingFeed AS src
    ON tgt.PartyId = src.PartyId
    WHEN MATCHED THEN
        UPDATE SET tgt.RegionRiskRating = src.NewRating, tgt.LastSyncDate = GETDATE()
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (PartyId, RegionRiskRating, LastSyncDate)
        VALUES (src.PartyId, src.NewRating, GETDATE())
    OUTPUT $action, inserted.PartyId, deleted.RegionRiskRating, inserted.RegionRiskRating
        INTO audit.RatingSyncLog (Action, PartyId, OldRating, NewRating);
END
