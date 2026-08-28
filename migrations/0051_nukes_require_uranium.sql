-- Migration: 0051 - Nukes require uranium
-- Date: 2026-08-27
-- Player feedback (Unknown Identity, Discord DM to Dede, 2026-08-27): the
-- revenue page's coalition tax and nukes-not-needing-uranium were both
-- flagged. Dede agreed nukes should cost uranium ("it is what makes a nuke
-- a nuke"). Nukes previously only cost aluminium/components/gasoline
-- (migration 0043) with no strategic/fissile-material input at all.
--
-- Uranium mines produce 40/tick, close to oil refineries' 44/tick which
-- gasoline is priced against for nukes (25000 gasoline). Scaling the same
-- way gives ~20000 uranium -- a meaningful but not economy-breaking cost.
-- ICBMs are left untouched; only "nukes" was reported.

BEGIN;

ALTER TABLE unit_dictionary ADD COLUMN IF NOT EXISTS production_cost_uranium BIGINT DEFAULT 0;

UPDATE unit_dictionary
SET production_cost_uranium = 20000
WHERE name = 'nukes';

COMMIT;
