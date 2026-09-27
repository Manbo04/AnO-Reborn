-- Migration: 0085 - Per-operation spy cooldowns + Counter-Intelligence Agents
-- Date: 2026-09-27
--
-- Discord #military-recommendations (germanicusjuliuscaesar, 2026-09-16,
-- Kaiser +1 on counter-espionage), approved by Dede:
--
--   1. "spying on resources, units and sabotaging resources can be done over
--      and over. But assassinating, or sabotaging nukes, missiles etc should
--      have cool downs." spyinfo only recorded (spyer, spyee, date), so the
--      12h cooldown had to be one flat timer across every operation. This adds
--      spyinfo.spy_type so app_core/intelligence/services.py can keep a
--      separate cooldown per op type (SPY_OP_COOLDOWNS). Rows written before
--      this migration keep spy_type NULL; the service counts a NULL row
--      against every op type's cooldown, so nothing gets a free reset at
--      deploy time.
--
--   3. "we need anti spy stuff... a sort of Counter Intelligence that
--      captures/kills spies, drives off the rest and saves whatever was about
--      to happen." New unit counter_intel_agents (an internal security force),
--      bought/sold on the military page like spies, with an hourly upkeep
--      through the normal unit-maintenance tick. Gold price lives in
--      variables.MILDICT, like every other unit. spyinfo.intercepted marks
--      operations foiled by the target's counter-intelligence.
--
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS spy_type TEXT;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS intercepted BOOLEAN NOT NULL DEFAULT FALSE;

-- Cooldown lookup: latest op per (spyer, spy_type).
CREATE INDEX IF NOT EXISTS idx_spyinfo_spyer_type_date
    ON spyinfo (spyer, spy_type, date DESC);

INSERT INTO unit_dictionary (
    name, display_name, combat_type, base_attack, base_defense,
    maintenance_cost_resource_id, maintenance_cost_amount, manpower_required,
    production_cost_rations, production_cost_components, production_cost_steel,
    production_cost_fuel, production_cost_aluminium, production_cost_uranium,
    description
)
SELECT
    'counter_intel_agents', 'Counter-Intelligence Agents', 'espionage', 0.0, 0.0,
    (SELECT resource_id FROM resource_dictionary WHERE name = 'rations'), 2, 1,
    200, 1500, 0, 0, 0, 0,
    'Internal security force. Intercepts incoming enemy spy operations before they happen, capturing some of the enemy spies.'
ON CONFLICT (name) DO NOTHING;

COMMIT;
