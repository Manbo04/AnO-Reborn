-- MIGRATION 0033: Optimize Schema
-- Purpose:
--   1) Add missing indexes to foreign keys across various active tables.
--   2) Clean up Prisma/Next.js generated duplicate tables that are schema bloat in this Python app.
--   3) Clean up old legacy tables from previous normalizations that are no longer actively populated.

BEGIN;

-- --------------------------------------------------------------------------
-- 1) Add Missing Indexes on Foreign Keys
-- --------------------------------------------------------------------------

-- Treaties
CREATE INDEX IF NOT EXISTS idx_treaties_col1_id ON treaties(col1_id);
CREATE INDEX IF NOT EXISTS idx_treaties_col2_id ON treaties(col2_id);
CREATE INDEX IF NOT EXISTS idx_treaties_status ON treaties(status);

-- Peace
CREATE INDEX IF NOT EXISTS idx_peace_author ON peace(author);

-- Coalition Applications (colId index already created in 0017)
CREATE INDEX IF NOT EXISTS idx_col_applications_userid ON col_applications(userId);

-- Coalition Banks Requests
CREATE INDEX IF NOT EXISTS idx_colBanksRequests_reqId ON colBanksRequests(reqId);
CREATE INDEX IF NOT EXISTS idx_colBanksRequests_colId ON colBanksRequests(colId);

-- Audits & Taxes
CREATE INDEX IF NOT EXISTS idx_purchase_audit_user_id ON purchase_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_reparation_tax_winner ON reparation_tax(winner);
CREATE INDEX IF NOT EXISTS idx_reparation_tax_loser ON reparation_tax(loser);
CREATE INDEX IF NOT EXISTS idx_revenue_user_id ON revenue(user_id);

-- Administration & Metrics
CREATE INDEX IF NOT EXISTS idx_admin_actions_actor ON admin_actions(actor);
CREATE INDEX IF NOT EXISTS idx_admin_actions_user_id ON admin_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_game_economy_snapshots_resource ON game_economy_snapshots(resource_name);

-- Background Tasks
-- task_runs is (task_name PK, last_run) only — no status column exists in the real schema.
CREATE INDEX IF NOT EXISTS idx_task_runs_task_name ON task_runs(task_name);

-- Polls
CREATE INDEX IF NOT EXISTS idx_poll_votes_user_id ON poll_votes(user_id);
CREATE INDEX IF NOT EXISTS idx_poll_votes_poll_name ON poll_votes(poll_name);

-- Discord Integration
CREATE INDEX IF NOT EXISTS idx_discord_role_aliases_guild_id ON discord_role_aliases(guild_id);
CREATE INDEX IF NOT EXISTS idx_discord_guild_settings_guild_id ON discord_guild_settings(guild_id);


-- --------------------------------------------------------------------------
-- 2) Remove Duplicate Next.js / Prisma Tables (Schema Bloat)
-- --------------------------------------------------------------------------
-- These CamelCase tables were created by Next.js/Prisma but are duplicates 
-- of our raw Postgres tables (users, provinces, stats).
DROP TABLE IF EXISTS "User" CASCADE;
DROP TABLE IF EXISTS "Nation" CASCADE;
DROP TABLE IF EXISTS "Province" CASCADE;
DROP TABLE IF EXISTS "Session" CASCADE;
DROP TABLE IF EXISTS "Account" CASCADE;
DROP TABLE IF EXISTS "VerificationToken" CASCADE;
DROP TABLE IF EXISTS "_prisma_migrations" CASCADE;


-- --------------------------------------------------------------------------
-- 3) Clean up old legacy tables from the normalization process
-- --------------------------------------------------------------------------
-- These were kept as backups in migration 0005. wars_legacy is genuinely
-- unused (no app code references it) and safe to drop. coalitions_legacy is
-- NOT bloat -- get_coalition_members_table() (database.py) actively prefers
-- it, and every _members_tbl() call in app_core/coalitions/routes.py reads
-- and writes it; migration 0059 (2026-09-01) even added a column to it.
-- Dropping it here would destroy the live coalition-membership table.
-- This line was never reached before this file's own column-name bugs
-- (fixed 2026-09-04) made every prior run of this migration abort earlier
-- in the same transaction -- do not restore the DROP.
DROP TABLE IF EXISTS wars_legacy CASCADE;

COMMIT;
