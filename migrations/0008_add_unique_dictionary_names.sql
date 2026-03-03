-- Migration 0008: Add UNIQUE constraint on dictionary name columns
-- Purpose: Prevent duplicate dictionary entries and ensure referential integrity
-- Date: 2026-03-02

BEGIN;

-- Add unique constraint on unit_dictionary.name
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'unit_dictionary_name_unique' AND conrelid = 'unit_dictionary'::regclass
  ) THEN
    ALTER TABLE unit_dictionary ADD CONSTRAINT unit_dictionary_name_unique UNIQUE (name);
  END IF;
END $$;

-- Add unique constraint on building_dictionary.name
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'building_dictionary_name_unique' AND conrelid = 'building_dictionary'::regclass
  ) THEN
    ALTER TABLE building_dictionary ADD CONSTRAINT building_dictionary_name_unique UNIQUE (name);
  END IF;
END $$;

-- Add unique constraint on tech_dictionary.name
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tech_dictionary_name_unique' AND conrelid = 'tech_dictionary'::regclass
  ) THEN
    ALTER TABLE tech_dictionary ADD CONSTRAINT tech_dictionary_name_unique UNIQUE (name);
  END IF;
END $$;

-- Add unique constraint on resource_dictionary.name
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'resource_dictionary_name_unique' AND conrelid = 'resource_dictionary'::regclass
  ) THEN
    ALTER TABLE resource_dictionary ADD CONSTRAINT resource_dictionary_name_unique UNIQUE (name);
  END IF;
END $$;

COMMIT;
