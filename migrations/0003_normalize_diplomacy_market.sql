-- Migration: Normalize Diplomacy and Global Market Tables
-- Date: 2026-03-02
-- Purpose: Continue normalized architecture with coalition membership, unified market, and war referential integrity
--
-- Key Changes:
-- 1. Create normalized Coalitions structure (core table + membership mapping)
-- 2. Create unified GlobalMarket table to replace separate trades/offers/requests
-- 3. Refactor Wars table to enforce strict foreign keys for attacker/defender
-- 4. Enforce strict foreign key constraints with appropriate cascade rules
-- 5. Create indexes for optimal query performance

-- ============================================================================
-- ALLIANCE/COALITION NORMALIZATION
-- ============================================================================

-- Create Coalitions table to store alliance definitions
CREATE TABLE IF NOT EXISTS coalitions_normalized (
    coalition_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    bank_balance BIGINT NOT NULL DEFAULT 0 CHECK (bank_balance >= 0),
    founder_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE,
    CONSTRAINT fk_coalition_founder FOREIGN KEY (founder_id)
        REFERENCES users(id) ON DELETE SET NULL
);

-- Create CoalitionMembers mapping table to track membership and roles
CREATE TABLE IF NOT EXISTS coalition_members (
    user_id INTEGER NOT NULL,
    coalition_id INTEGER NOT NULL,
    role VARCHAR(40) NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (user_id, coalition_id),
    CONSTRAINT fk_coalition_member_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_coalition_member_coalition FOREIGN KEY (coalition_id)
        REFERENCES coalitions_normalized(coalition_id) ON DELETE CASCADE,
    CONSTRAINT coalition_valid_role CHECK (
        role IN ('founder', 'leader', 'officer', 'member')
    )
);

-- Indexes for optimal query performance on CoalitionMembers
CREATE INDEX IF NOT EXISTS idx_coalition_members_user_id ON coalition_members(user_id);
CREATE INDEX IF NOT EXISTS idx_coalition_members_coalition_id ON coalition_members(coalition_id);
CREATE INDEX IF NOT EXISTS idx_coalition_members_role ON coalition_members(role);

-- ============================================================================
-- UNIFIED GLOBAL MARKET
-- ============================================================================

-- Create GlobalMarket table to replace trades, offers, and requests
CREATE TABLE IF NOT EXISTS global_market (
    market_id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    price_per_unit DECIMAL(15, 2) NOT NULL CHECK (price_per_unit > 0),
    offer_type VARCHAR(20) NOT NULL DEFAULT 'sell',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE,
    fulfilled_by INTEGER,
    fulfilled_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_global_market_seller FOREIGN KEY (seller_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_global_market_resource FOREIGN KEY (resource_id)
        REFERENCES resource_dictionary(resource_id) ON DELETE RESTRICT,
    CONSTRAINT fk_global_market_fulfilled_by FOREIGN KEY (fulfilled_by)
        REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT market_valid_offer_type CHECK (
        offer_type IN ('sell', 'buy', 'trade')
    ),
    CONSTRAINT market_valid_status CHECK (
        status IN ('active', 'fulfilled', 'cancelled', 'expired')
    )
);

-- Indexes for optimal query performance on GlobalMarket
CREATE INDEX IF NOT EXISTS idx_global_market_seller_id ON global_market(seller_id);
CREATE INDEX IF NOT EXISTS idx_global_market_resource_id ON global_market(resource_id);
CREATE INDEX IF NOT EXISTS idx_global_market_status ON global_market(status);
CREATE INDEX IF NOT EXISTS idx_global_market_offer_type ON global_market(offer_type);
CREATE INDEX IF NOT EXISTS idx_global_market_created_at ON global_market(created_at DESC);

-- ============================================================================
-- WARFARE REFERENTIAL INTEGRITY
-- ============================================================================

-- Create Wars table with strict foreign key constraints
-- Note: Using CREATE TABLE IF NOT EXISTS to avoid conflicts with existing wars table
-- If wars table exists, manual ALTER TABLE commands may be needed in DBeaver
CREATE TABLE IF NOT EXISTS wars_normalized (
    war_id SERIAL PRIMARY KEY,
    attacker_id INTEGER NOT NULL,
    defender_id INTEGER NOT NULL,
    war_type VARCHAR(50) NOT NULL,
    aggressor_message VARCHAR(240),
    peace_date TIMESTAMP WITH TIME ZONE,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    attacker_supplies INTEGER DEFAULT 200 CHECK (attacker_supplies >= 0),
    defender_supplies INTEGER DEFAULT 200 CHECK (defender_supplies >= 0),
    last_visited TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    attacker_morale INTEGER DEFAULT 100 CHECK (attacker_morale >= 0 AND attacker_morale <= 100),
    defender_morale INTEGER DEFAULT 100 CHECK (defender_morale >= 0 AND defender_morale <= 100),
    peace_offer_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    winner_id INTEGER,
    CONSTRAINT fk_wars_attacker FOREIGN KEY (attacker_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_wars_defender FOREIGN KEY (defender_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_wars_winner FOREIGN KEY (winner_id)
        REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT wars_valid_status CHECK (
        status IN ('active', 'ended', 'peace', 'surrender')
    ),
    CONSTRAINT wars_different_parties CHECK (attacker_id != defender_id)
);

-- Indexes for optimal query performance on Wars
CREATE INDEX IF NOT EXISTS idx_wars_attacker_id ON wars_normalized(attacker_id);
CREATE INDEX IF NOT EXISTS idx_wars_defender_id ON wars_normalized(defender_id);
CREATE INDEX IF NOT EXISTS idx_wars_status ON wars_normalized(status);
CREATE INDEX IF NOT EXISTS idx_wars_start_date ON wars_normalized(start_date DESC);

-- Composite index for finding active wars involving a specific user
CREATE INDEX IF NOT EXISTS idx_wars_user_active ON wars_normalized(attacker_id, defender_id, status)
    WHERE status = 'active';

-- ============================================================================
-- MIGRATION NOTES FOR MANUAL EXECUTION
-- ============================================================================
--
-- IMPORTANT: This migration creates NEW normalized tables alongside existing ones:
-- - coalitions_normalized (replaces flat coalitions table)
-- - coalition_members (new mapping table)
-- - global_market (replaces offers, trades, requests tables)
-- - wars_normalized (replaces wars table with strict foreign keys)
--
-- DATA MIGRATION STEPS (to be executed manually in DBeaver):
--
-- 1. Coalition Migration:
--    a. Inspect existing coalitions table structure
--    b. Create entries in coalitions_normalized for unique colId values
--    c. Migrate userId, colId, role -> coalition_members table
--    d. Verify foreign key constraints are satisfied
--    e. When ready: DROP TABLE coalitions; RENAME coalitions_normalized TO coalitions;
--
-- 2. Market Migration:
--    a. Inspect existing offers/trades/requests tables
--    b. Map resource VARCHAR to resource_id via resource_dictionary lookup
--    c. Insert into global_market with appropriate offer_type
--    d. Verify foreign key constraints are satisfied
--    e. When ready: DROP old tables and remove _normalized suffix if used
--
-- 3. Wars Migration:
--    a. Backup existing wars table data
--    b. Verify attacker and defender columns reference valid user IDs
--    c. Migrate data to wars_normalized with proper timestamp conversion
--    d. Verify foreign key constraints are satisfied
--    e. When ready: DROP TABLE wars; RENAME wars_normalized TO wars;
--
-- FOREIGN KEY ENFORCEMENT:
-- All new tables enforce referential integrity at the database level.
-- Attempting to insert invalid user_id, coalition_id, or resource_id will fail.
--
-- ============================================================================
-- INTEGRITY NOTES
-- ============================================================================
--
-- Foreign Key Constraints:
-- - coalition_members.user_id → users.id with ON DELETE CASCADE
--   (Membership removed when user deleted)
-- - coalition_members.coalition_id → coalitions_normalized.coalition_id with ON DELETE CASCADE
--   (All memberships removed when coalition disbanded)
--
-- - global_market.seller_id → users.id with ON DELETE CASCADE
--   (Market offers removed when seller account deleted)
-- - global_market.resource_id → resource_dictionary.resource_id with ON DELETE RESTRICT
--   (Cannot delete resource definitions while active market offers exist)
-- - global_market.fulfilled_by → users.id with ON DELETE SET NULL
--   (Preserves transaction history even if buyer deleted)
--
-- - wars_normalized.attacker_id → users.id with ON DELETE CASCADE
--   (War record removed if attacker deleted)
-- - wars_normalized.defender_id → users.id with ON DELETE CASCADE
--   (War record removed if defender deleted)
-- - wars_normalized.winner_id → users.id with ON DELETE SET NULL
--   (Preserves war outcome even if winner deleted)
--
-- Indexes:
-- - Coalition: Fast lookups by user, coalition, or role
-- - Market: Fast filtering by seller, resource, status, offer type, and time
-- - Wars: Fast queries for active wars, user involvement, and historical data
--
-- CHECK Constraints:
-- - coalition_members.role: Must be founder/leader/officer/member
-- - global_market.quantity > 0: No zero-quantity offers
-- - global_market.price_per_unit > 0: No free or negative pricing
-- - global_market.offer_type: Must be sell/buy/trade
-- - global_market.status: Must be active/fulfilled/cancelled/expired
-- - wars_normalized.supplies >= 0: No negative war supplies
-- - wars_normalized.morale: Must be between 0 and 100
-- - wars_normalized.attacker_id != defender_id: Cannot declare war on self
-- - wars_normalized.status: Must be active/ended/peace/surrender
