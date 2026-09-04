-- Buy Me a Coffee one-time Gem purchases (Extras), alongside the existing
-- Stripe gem_purchases ledger -- see app_core/store/routes.py::bmc_webhook.
-- Stripe is built but can't go live (unverified legal entity); BMC's
-- "Extras" shop + a required custom question ("your AnO username") is the
-- workaround: the webhook payload carries the buyer's typed answer, so
-- purchases can still be credited automatically without our own checkout
-- flow initiating the session (unlike Stripe, there's no "pending" step --
-- the webhook only fires after payment succeeds).
BEGIN;

-- Maps a gem_packages row to the specific BMC "Extra" shop item that sells
-- it, so the webhook can look up which package (and thus how many Gems) a
-- given extra_purchase line item corresponds to.
ALTER TABLE gem_packages
    ADD COLUMN IF NOT EXISTS bmc_extra_id INTEGER UNIQUE;

-- BMC's Extras price field only accepts whole-dollar amounts (no cents --
-- confirmed live in the creator dashboard). This is deliberately a separate
-- column from price_cents (the Stripe price, e.g. $2.99) rather than
-- reusing/overwriting it: the two checkouts can legitimately charge
-- different amounts for the same Gems, and the Store page must render
-- whichever price a given "Buy" button will actually charge.
ALTER TABLE gem_packages
    ADD COLUMN IF NOT EXISTS bmc_price_cents INTEGER;

-- One row per extras[] line item per BMC order (an order can contain
-- multiple different Extras). status='unmatched' means the buyer's typed
-- username didn't resolve to an AnO account -- Gems are NOT credited in
-- that case; it's logged for manual follow-up rather than guessed at.
CREATE TABLE IF NOT EXISTS bmc_gem_purchases (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    gem_package_id BIGINT REFERENCES gem_packages(id),
    bmc_transaction_id TEXT NOT NULL,
    bmc_extra_line_id INTEGER NOT NULL,
    claimed_username TEXT,
    supporter_email TEXT,
    supporter_name TEXT,
    amount NUMERIC,
    currency TEXT,
    gems_granted BIGINT,
    status TEXT NOT NULL DEFAULT 'credited'
        CHECK (status IN ('credited', 'refunded', 'unmatched')),
    credited_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    raw_event JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bmc_transaction_id, bmc_extra_line_id)
);
CREATE INDEX IF NOT EXISTS idx_bmc_gem_purchases_user_id ON bmc_gem_purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_bmc_gem_purchases_status ON bmc_gem_purchases(status);

COMMIT;
