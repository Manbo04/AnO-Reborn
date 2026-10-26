-- New wars start at 150 morale, 1.5x the live 100-point clock.
-- Active and finished wars are scaled once so the share already lost stays
-- the same (40/100 becomes 60/150). Safe to re-run: the flag blocks a second
-- multiply, and new rows default to already being on the long clock.
ALTER TABLE wars ADD COLUMN IF NOT EXISTS morale_on_long_clock boolean NOT NULL DEFAULT false;

ALTER TABLE wars ALTER COLUMN attacker_morale SET DEFAULT 150;
ALTER TABLE wars ALTER COLUMN defender_morale SET DEFAULT 150;
ALTER TABLE wars ALTER COLUMN morale_on_long_clock SET DEFAULT true;

UPDATE wars
SET attacker_morale = LEAST(150, CAST(ROUND(attacker_morale * 1.5) AS integer)),
    defender_morale = LEAST(150, CAST(ROUND(defender_morale * 1.5) AS integer)),
    morale_on_long_clock = TRUE
WHERE morale_on_long_clock = FALSE;
