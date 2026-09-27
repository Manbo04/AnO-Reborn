-- Migration: 0083 - Currency unions
-- Date: 2026-09-27
--
-- Discord #suggestions (luciuskonst, 2026-09-25, "Economy tweaks/ideas
-- laundry list" #6, +1 from fikusmikus): nations can form a currency union
-- that shares one currency and gives its members benefits. Benefits apply
-- only while a union has at least 2 members (app_core/currency_unions):
--   * trades between members pay the reduced union trade fee
--   * members' bond issuance cap is raised
-- A nation can belong to at most one union (currency_union_members PK).

BEGIN;

CREATE TABLE IF NOT EXISTS currency_unions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(60) NOT NULL,
    currency_name VARCHAR(40) NOT NULL,
    founder_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS currency_unions_name_lower_uniq
    ON currency_unions (LOWER(name));

CREATE TABLE IF NOT EXISTS currency_union_members (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    union_id INTEGER NOT NULL REFERENCES currency_unions(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS currency_union_members_union_idx
    ON currency_union_members (union_id);

CREATE TABLE IF NOT EXISTS currency_union_applications (
    union_id INTEGER NOT NULL REFERENCES currency_unions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (union_id, user_id)
);

COMMIT;
