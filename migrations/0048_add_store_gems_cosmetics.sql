-- Migration: 0048 - Store: premium currency ("Gems") + cosmetics
-- Date: 2026-08-26
-- Adds a premium currency ("Gems", purchased with real money) plus a
-- real-money package catalog + payment ledger (Stripe), a curated cosmetics
-- catalog (starting with page backgrounds), and per-user ownership/equip
-- state. See app_core/store/ for the blueprint that uses this schema.

BEGIN;

-- Premium currency balance. Mirrors stats.gold: a dedicated column rather
-- than a resource_dictionary/user_economy row, since Gems are not a
-- tradeable production resource.
ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS gems BIGINT NOT NULL DEFAULT 0
        CHECK (gems >= 0);

-- Curated, admin-managed catalog of real-money -> Gems packages
-- (e.g. $4.99 -> 500 Gems). No user-facing write path.
CREATE TABLE IF NOT EXISTS gem_packages (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    gems_granted BIGINT NOT NULL CHECK (gems_granted > 0),
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    currency TEXT NOT NULL DEFAULT 'usd',
    stripe_price_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Real-money transaction ledger. One row per Stripe Checkout Session.
-- This table is the idempotency boundary: Gems are only ever credited once
-- per row (see the UNIQUE constraints below plus the status state machine
-- enforced in app_core/store/repositories.py::mark_gem_purchase_credited).
CREATE TABLE IF NOT EXISTS gem_purchases (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gem_package_id BIGINT NOT NULL REFERENCES gem_packages(id),
    stripe_checkout_session_id TEXT UNIQUE,
    stripe_payment_intent_id TEXT UNIQUE,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    gems_granted BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'credited', 'failed', 'refunded', 'chargeback')),
    credited_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    raw_event JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gem_purchases_user_id ON gem_purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_gem_purchases_status ON gem_purchases(status);

-- Curated cosmetics catalog. v1 scope: page-background cosmetics only.
CREATE TABLE IF NOT EXISTS cosmetics (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    cosmetic_type TEXT NOT NULL DEFAULT 'background'
        CHECK (cosmetic_type IN ('background')),
    price_gems BIGINT NOT NULL CHECK (price_gems > 0),
    css_class TEXT NOT NULL,
    preview_image_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-user ownership of purchased cosmetics.
CREATE TABLE IF NOT EXISTS user_cosmetics (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cosmetic_id BIGINT NOT NULL REFERENCES cosmetics(id) ON DELETE CASCADE,
    purchased_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    gems_spent BIGINT NOT NULL,
    UNIQUE (user_id, cosmetic_id)
);
CREATE INDEX IF NOT EXISTS idx_user_cosmetics_user_id ON user_cosmetics(user_id);

-- Which cosmetic (if any) is currently equipped. NULL = default theme
-- background. ON DELETE SET NULL so retiring a cosmetic from the catalog
-- silently falls equipped players back to the default rather than erroring.
ALTER TABLE stats
    ADD COLUMN IF NOT EXISTS equipped_background_cosmetic_id BIGINT
        REFERENCES cosmetics(id) ON DELETE SET NULL;

COMMIT;
