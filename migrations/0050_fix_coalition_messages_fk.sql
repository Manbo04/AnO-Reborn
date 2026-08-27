-- 0047 pointed coalition_messages.coalition_id at coalitions_normalized(coalition_id),
-- an abandoned table left over from an old normalization attempt (0 rows in prod).
-- Every real coalition id used app-wide (colId) lives in colnames(id) instead --
-- every other coalition FK in the schema (coalition_invites, colbanks, requests,
-- treaties, coalitions_legacy, ...) already points there. Because of the wrong
-- reference, every coalition_chat_message insert violated the FK and was rolled
-- back -- the message disappeared from the input with no error and never reached
-- the table.
ALTER TABLE coalition_messages
    DROP CONSTRAINT IF EXISTS coalition_messages_coalition_id_fkey;

ALTER TABLE coalition_messages
    ADD CONSTRAINT coalition_messages_coalition_id_fkey
    FOREIGN KEY (coalition_id) REFERENCES colnames(id) ON DELETE CASCADE;
