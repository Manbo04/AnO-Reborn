-- Add persistent manpower storage to stats
ALTER TABLE stats
ADD COLUMN IF NOT EXISTS manpower INTEGER NOT NULL DEFAULT 0;
