-- Migration: 0056 - Widen users.description (National Lore) to TEXT
-- Date: 2026-08-31
-- The National Lore editor is a full markdown editor with prompt chips that
-- encourage multi-section lore (Founding/Government/Diplomacy/Culture), but
-- the column was only varchar(500). Saving longer lore hit Postgres'
-- "value too long for type character varying(500)" as an unhandled
-- exception in update_info(), surfacing as a 500 (reported: ticket-0026).

BEGIN;

ALTER TABLE users ALTER COLUMN description TYPE TEXT;

COMMIT;
