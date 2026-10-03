-- 0100_add_news_is_read.sql
-- Track read/seen state for player news and reports so viewing the News tab
-- clears notification bubbles while preserving full report history.

ALTER TABLE news ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT TRUE;
ALTER TABLE news ALTER COLUMN is_read SET DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_news_dest_is_read ON news(destination_id, is_read);
