-- Add default_defense to stats table (migrated from dropped military table)
ALTER TABLE stats
ADD COLUMN IF NOT EXISTS default_defense TEXT NOT NULL DEFAULT 'soldiers,tanks,artillery';
