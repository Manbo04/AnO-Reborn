-- World Assembly: sanction severity, resolution duration, commend resolutions.
-- duration_days: NULL = default (14), 0 = indefinite. severity: minor/regular/major
-- (legacy sanctions have NULL severity and behave as 'regular').
ALTER TABLE assembly_proposals ADD COLUMN IF NOT EXISTS severity VARCHAR(16);
ALTER TABLE assembly_proposals ADD COLUMN IF NOT EXISTS duration_days INTEGER;
ALTER TABLE assembly_effects ADD COLUMN IF NOT EXISTS severity VARCHAR(16);
