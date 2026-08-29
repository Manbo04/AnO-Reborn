-- Migration: 0052 - Patreon monthly Gems bonus
-- Date: 2026-08-29
-- Adds an admin-managed Patreon-tier -> Gems mapping and an idempotent
-- grant ledger for crediting Gems to patrons once a month. Dormant until
-- FEATURE_PATREON_GEMS is turned on, PATREON_ACCESS_TOKEN/PATREON_CAMPAIGN_ID
-- are configured, and patreon_tiers is seeded with real values -- see
-- app_core/patreon/. Mirrors the gems ledger pattern from 0048.

BEGIN;

-- Admin-managed catalog: Patreon tier title -> monthly Gems grant. Matched
-- by title against the campaign's real tiers (see
-- app_core/patreon/client.py::fetch_active_members). No user-facing write
-- path -- deliberately empty until seeded with the real tier list.
CREATE TABLE IF NOT EXISTS patreon_tiers (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL UNIQUE,
    gems_per_month BIGINT NOT NULL CHECK (gems_per_month > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per user per calendar month the bonus was granted. The
-- UNIQUE(user_id, period) constraint is the idempotency boundary -- a
-- retried/re-run task can never double-credit the same user in the same
-- month (see app_core/patreon/repositories.py::grant_monthly_gems).
CREATE TABLE IF NOT EXISTS patreon_gem_grants (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    patreon_member_id TEXT NOT NULL,
    tier_title TEXT NOT NULL,
    period TEXT NOT NULL, -- 'YYYY-MM', UTC
    gems_granted BIGINT NOT NULL CHECK (gems_granted > 0),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, period)
);
CREATE INDEX IF NOT EXISTS idx_patreon_gem_grants_user_id ON patreon_gem_grants(user_id);

COMMIT;
