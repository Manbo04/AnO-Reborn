-- First-party player analytics (applied to prod 2026-09-29).
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_referrer_host TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_landing_path TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_utm_source TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_utm_medium TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_utm_campaign TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_country CHAR(2);
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_device TEXT;        -- mobile|tablet|desktop
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_heard_from TEXT;     -- self-reported answer
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_channel_source TEXT; -- 'tracked' | 'backfill'
CREATE TABLE IF NOT EXISTS site_visits (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  day DATE NOT NULL DEFAULT CURRENT_DATE,
  visitor_hash TEXT NOT NULL,       -- daily-rotating anonymous hash, never raw IP
  user_id INTEGER,                  -- NULL for logged-out visitors
  path TEXT NOT NULL,
  referrer_host TEXT,               -- only external referrers, else NULL
  utm_source TEXT, utm_medium TEXT, utm_campaign TEXT,
  country CHAR(2), device TEXT
);
CREATE INDEX IF NOT EXISTS site_visits_day_idx ON site_visits(day);
CREATE TABLE IF NOT EXISTS user_active_days (
  user_id INTEGER NOT NULL,
  day DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'tracked',  -- 'tracked' or backfill origin name
  PRIMARY KEY (user_id, day)
);
CREATE INDEX IF NOT EXISTS user_active_days_day_idx ON user_active_days(day);
