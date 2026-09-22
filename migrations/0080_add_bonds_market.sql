-- Migration: 0080 - Player-to-player Bonds market
-- Date: 2026-09-22
--
-- Requested by Kurai in #suggestions (2026-09-16): distinct from the
-- national loan system (app_core/loans/, migration 0069) where a nation
-- borrows from the game itself -- here one player funds another player's
-- bond directly, with daily interest paid automatically and a real
-- enforcement mechanism if the borrower defaults (see
-- app_core/game_ticks/bond_tick.py). Kurai's ask: issuers set rate+term
-- before a bond sells, bonds can't be cashed out before maturity, daily
-- interest is auto-deducted to the lender, and issuers can optionally
-- escrow part of the principal ahead of maturity instead of a lump sum.

BEGIN;

CREATE TABLE IF NOT EXISTS bonds (
    id SERIAL PRIMARY KEY,
    issuer_id INTEGER NOT NULL REFERENCES users(id),
    lender_id INTEGER REFERENCES users(id),
    principal NUMERIC NOT NULL,
    daily_interest_rate NUMERIC NOT NULL,
    term_days INTEGER NOT NULL,
    auto_escrow BOOLEAN NOT NULL DEFAULT FALSE,
    escrowed_principal NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'listed',
    default_strikes INTEGER NOT NULL DEFAULT 0,
    garnishment_owed NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    funded_at TIMESTAMPTZ,
    matures_at TIMESTAMPTZ,
    last_tick_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT bonds_no_self_lending CHECK (lender_id IS NULL OR lender_id <> issuer_id),
    CONSTRAINT bonds_status_check CHECK (status IN ('listed', 'active', 'repaid', 'defaulted', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_bonds_status ON bonds (status);
CREATE INDEX IF NOT EXISTS idx_bonds_issuer ON bonds (issuer_id);
CREATE INDEX IF NOT EXISTS idx_bonds_lender ON bonds (lender_id);

COMMENT ON TABLE bonds IS
    'Player-to-player lending: issuer lists a bond (rate+term fixed once it sells), a lender funds it (principal transferred issuer<-lender immediately, see app_core/bonds/services.py::fund_bond), then app_core/game_ticks/bond_tick.py garnishes daily interest issuer->lender automatically until maturity. auto_escrow issuers also amortize principal daily into escrowed_principal, paid to the lender at maturity alongside any final interest; non-escrow issuers owe the full principal as a lump sum at maturity. Missing BOND_MAX_DEFAULT_STRIKES daily interest payments force-defaults a bond early instead of waiting for a maturity cliff; any shortfall not covered by escrow becomes garnishment_owed, which the tick keeps collecting from the issuer even after default -- so defaulting is never zero-cost. A defaulted issuer is also blocked from issuing new bonds for BOND_DEFAULT_COOLDOWN_DAYS. Deliberately separate from the sibling national-loan system (user_loans, migration 0069) where a nation borrows from the game itself rather than another player.';

COMMIT;
