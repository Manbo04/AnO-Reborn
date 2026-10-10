-- Migration: 20261010_1520_coalition_embargoes
-- Coalition-level embargoes (JOB D1)
--
-- Enables a coalition to embargo another coalition: every member of the
-- embargoing coalition is blocked from trading with every member of the
-- target coalition on the market and via direct trade offers.

CREATE TABLE IF NOT EXISTS coalition_embargoes (
    embargoer_coalition_id INTEGER NOT NULL REFERENCES colnames(id) ON DELETE CASCADE,
    target_coalition_id INTEGER NOT NULL REFERENCES colnames(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (embargoer_coalition_id, target_coalition_id),
    CHECK (embargoer_coalition_id <> target_coalition_id)
);

CREATE INDEX IF NOT EXISTS idx_coalition_embargoes_target ON coalition_embargoes(target_coalition_id);

COMMENT ON TABLE coalition_embargoes IS
    'Coalition-level embargoes: embargoer coalition blocks all trades between its members and target coalition members.';
