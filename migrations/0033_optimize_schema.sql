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

-- Coalition Applications
CREATE INDEX IF NOT EXISTS idx_col_applications_col_id ON col_applications(col_id);
CREATE INDEX IF NOT EXISTS idx_col_applications_user_id ON col_applications(user_id);

-- Coalition Banks Requests
CREATE INDEX IF NOT EXISTS idx_colBanksRequests_reqId ON colBanksRequests(reqId);
CREATE INDEX IF NOT EXISTS idx_colBanksRequests_colId ON colBanksRequests(colId);

-- Audits & Taxes
CREATE INDEX IF NOT EXISTS idx_purchase_audit_user_id ON purchase_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_reparation_tax_sender_id ON reparation_tax(sender_id);
CREATE INDEX IF NOT EXISTS idx_reparation_tax_receiver_id ON reparation_tax(receiver_id);
CREATE INDEX IF NOT EXISTS idx_revenue_user_id ON revenue(user_id);

-- Administration & Metrics
CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_id ON admin_actions(admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_actions_target_user_id ON admin_actions(target_user_id);
CREATE INDEX IF NOT EXISTS idx_game_economy_snapshots_resource ON game_economy_snapshots(resource);

-- Background Tasks
CREATE INDEX IF NOT EXISTS idx_task_runs_task_name ON task_runs(task_name);
CREATE INDEX IF NOT EXISTS idx_task_runs_status ON task_runs(status);

-- Polls
CREATE INDEX IF NOT EXISTS idx_poll_votes_user_id ON poll_votes(user_id);
CREATE INDEX IF NOT EXISTS idx_poll_votes_poll_id ON poll_votes(poll_id);

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
-- These were kept as backups in migration 0005 but are now redundant bloat.
DROP TABLE IF EXISTS coalitions_legacy CASCADE;
DROP TABLE IF EXISTS wars_legacy CASCADE;

COMMIT;
