-- ============================================================================
-- MIGRATION 0005: Final normalization cleanup
-- Purpose:
--   1) Drop legacy wide tables after verified migration
--   2) Rename normalized tables to final clean names
-- ============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- 1) Drop legacy wide tables (explicitly requested)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS proinfra CASCADE;
DROP TABLE IF EXISTS upgrades CASCADE;
DROP TABLE IF EXISTS military CASCADE;
DROP TABLE IF EXISTS resources CASCADE;

-- --------------------------------------------------------------------------
-- 2) Rename normalized tables to final names where applicable
-- --------------------------------------------------------------------------

-- Coalitions: keep old table as *_legacy if present, then promote normalized
DO $$
BEGIN
    IF to_regclass('public.coalitions_normalized') IS NOT NULL THEN
        IF to_regclass('public.coalitions') IS NOT NULL THEN
            IF to_regclass('public.coalitions_legacy') IS NULL THEN
                ALTER TABLE public.coalitions RENAME TO coalitions_legacy;
            END IF;
        END IF;

        IF to_regclass('public.coalitions') IS NULL THEN
            ALTER TABLE public.coalitions_normalized RENAME TO coalitions;
        END IF;
    END IF;
END $$;

-- Wars: promote normalized table if present (preserve old as *_legacy)
DO $$
BEGIN
    IF to_regclass('public.wars_normalized') IS NOT NULL THEN
        IF to_regclass('public.wars') IS NOT NULL THEN
            IF to_regclass('public.wars_legacy') IS NULL THEN
                ALTER TABLE public.wars RENAME TO wars_legacy;
            END IF;
        END IF;

        IF to_regclass('public.wars') IS NULL THEN
            ALTER TABLE public.wars_normalized RENAME TO wars;
        END IF;
    END IF;
END $$;

COMMIT;
