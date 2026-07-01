-- Migration 0024: Next.js Prisma → legacy compatibility views
--
-- Do NOT run this file blindly on a legacy-only database.
-- Prefer the introspection script (handles column name variants):
--
--   DATABASE_PUBLIC_URL=... python3 scripts/apply_nextjs_compat_views.py
--
-- This SQL documents the intended bridge when Prisma tables use the default
-- names User, Nation, Province. Adjust column names if your Prisma schema differs.

-- Example users view (userid must be User.id, not Nation.id):
-- CREATE OR REPLACE VIEW users AS
-- SELECT
--   u.id::text AS id,
--   COALESCE(n.name, u.username) AS username,
--   u.email,
--   COALESCE(u."createdAt"::text, to_char(now(), 'YYYY-MM-DD')) AS date,
--   u."passwordHash" AS hash,
--   u."discordId" AS discord_id,
--   COALESCE(u."isVerified", false) AS is_verified,
--   COALESCE(u."authType", 'normal') AS auth_type
-- FROM "User" u
-- LEFT JOIN "Nation" n ON n."userId" = u.id;

-- Views are applied via scripts/apply_nextjs_compat_views.py (introspective).
-- This file is a no-op placeholder so the migration runner records it as applied.
SELECT 1;
