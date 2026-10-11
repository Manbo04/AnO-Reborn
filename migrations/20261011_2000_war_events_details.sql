-- Store what each side sent/fielded and the army strengths for every fight,
-- so war results can be explained after the fact (war 557 could not be).
ALTER TABLE war_events ADD COLUMN IF NOT EXISTS details TEXT;
