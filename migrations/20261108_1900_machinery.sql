-- Machinery: first wear-out good (shadow mode; nothing consumes it until the ledger_wearout flag is on).
BEGIN;
INSERT INTO resource_dictionary (name, display_name, description, is_production, is_raw, is_active)
VALUES ('machinery', 'Machinery', 'Industrial machinery. Mines, mills and factories wear out and need it to run at full output.', true, false, true)
ON CONFLICT (name) DO NOTHING;
INSERT INTO user_economy (user_id, resource_id, quantity)
SELECT u.id, rd.resource_id, 0 FROM users u CROSS JOIN resource_dictionary rd WHERE rd.name = 'machinery'
ON CONFLICT (user_id, resource_id) DO NOTHING;
INSERT INTO building_dictionary (name, display_name, category, base_cost, effect_type, effect_value, maintenance_cost, description)
VALUES ('machinery_works', 'Machinery Works', 'resource_production', 14000000, 'resource_production', 24.00, 55000, 'Turns steel and components into machinery.')
ON CONFLICT (name) DO NOTHING;
ALTER TABLE spyinfo ADD COLUMN IF NOT EXISTS machinery BIGINT DEFAULT 0;
ALTER TABLE colbanks ADD COLUMN IF NOT EXISTS machinery BIGINT DEFAULT 0;
COMMIT;

BEGIN;
CREATE TABLE IF NOT EXISTS ledger_wear_state (
    user_id integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    fleet integer NOT NULL DEFAULT 0, need integer NOT NULL DEFAULT 0, stock bigint NOT NULL DEFAULT 0,
    cover numeric(6,4) NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL DEFAULT now());
INSERT INTO feature_flags (key, enabled, rollout_percent) VALUES ('ledger_wearout', false, 100) ON CONFLICT (key) DO NOTHING;
COMMIT;

BEGIN;
CREATE TABLE IF NOT EXISTS ledger_wear_meta (id integer PRIMARY KEY DEFAULT 1, ticks integer NOT NULL DEFAULT 0);
COMMIT;
