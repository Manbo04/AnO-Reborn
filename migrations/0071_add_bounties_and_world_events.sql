-- Migration: 0071 - Bounties, World Affairs feed, and two schema-drift backfills
-- Date: 2026-09-07
--
-- Part of the "more nation-to-nation interaction" feature: bounties let a nation
-- pay for another nation's defeat in war, and world_events backs a public
-- "World Affairs" feed (plus the existing news ticker) so sabotage/aid/alliance/
-- bounty/war/coalition-treaty events are visible sitewide, not just to the two
-- nations involved.
--
-- Also backfills two objects that exist in production but were never captured
-- in a tracked migration (found while building this feature against a fresh
-- local ano_staging, which was missing both): nation_treaties (originally
-- created by the standalone create_nation_treaties.py script) and
-- resource_dictionary.is_active (added by an unknown out-of-band ALTER at some
-- point). Both use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS so this is a no-op
-- against prod, which already has them.

BEGIN;

CREATE TABLE IF NOT EXISTS nation_treaties (
    id SERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    treaty_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE resource_dictionary ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS bounties (
    id SERIAL PRIMARY KEY,
    target_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    poster_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL CHECK (amount >= 1000),
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'claimed', 'cancelled')),
    claimed_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bounties_target_status ON bounties (target_id, status);
CREATE INDEX IF NOT EXISTS idx_bounties_poster ON bounties (poster_id);

CREATE TABLE IF NOT EXISTS world_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,
    message TEXT NOT NULL,
    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_world_events_created_at ON world_events (created_at DESC);

COMMENT ON TABLE bounties IS
    'A nation escrows gold against another nation''s defeat in war; paid out to whoever lands the war-concluding blow (attack_scripts/war_orchestrator.py persist_fight_results). Multiple open bounties on one target all pay out - crowd-sourced incentive, not a bug.';
COMMENT ON TABLE world_events IS
    'Sitewide public activity feed (wars, sabotage, aid, treaties, bounty claims, coalition treaties) - backs the /world_affairs page and feeds real entries into the existing news ticker (province.py get_global_events).';

COMMIT;
