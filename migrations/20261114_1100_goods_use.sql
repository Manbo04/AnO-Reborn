-- ledger_goods_use flag + state tables (realm only)
BEGIN;
CREATE TABLE IF NOT EXISTS ledger_goods_meta (id integer PRIMARY KEY DEFAULT 1, ticks integer NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ledger_goods_state (user_id integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  clothing numeric(6,4) NOT NULL DEFAULT 1, medicine numeric(6,4) NOT NULL DEFAULT 1, fertilizer numeric(6,4) NOT NULL DEFAULT 0,
  prosperity numeric(6,4) NOT NULL DEFAULT 0, happy numeric(8,3) NOT NULL DEFAULT 0, updated_at timestamptz NOT NULL DEFAULT now());
INSERT INTO feature_flags (key, enabled, rollout_percent) VALUES ('ledger_goods_use', false, 100) ON CONFLICT (key) DO NOTHING;
COMMIT;
