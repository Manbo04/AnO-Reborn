-- hidden_from_rankings: never listed on leaderboards/scores (owner + test account; bots are
-- excluded by auth_type in code as well). untargetable: other players can't interact with it.
ALTER TABLE users ADD COLUMN IF NOT EXISTS hidden_from_rankings BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS untargetable BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE users SET hidden_from_rankings = TRUE WHERE auth_type = 'bot' OR id IN (1, 16);
UPDATE users SET untargetable = TRUE WHERE id = 1;
