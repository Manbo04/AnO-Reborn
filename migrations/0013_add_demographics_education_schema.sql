-- Migration: Add Demographics and Education Schema
-- Date: 2026-03-04
-- Purpose: Expand population tracking from single integer to age-bracket and education-level demographics
--
-- Key Changes:
-- 1. Add age-bracket columns to provinces: pop_children, pop_working, pop_elderly
-- 2. Add education-level columns to provinces: edu_none, edu_highschool, edu_college
-- 3. Each column has default value of 0 and NOT NULL constraint
-- 4. No data transformation in this migration (handled by Python script)

-- ============================================================================
-- DEMOGRAPHICS SCHEMA EXPANSION
-- ============================================================================

-- Add age-bracket demographic columns to provinces table
ALTER TABLE provinces
ADD COLUMN IF NOT EXISTS pop_children INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS pop_working INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS pop_elderly INTEGER NOT NULL DEFAULT 0;

-- Add education-level columns to provinces table (tracks education of pop_working pool)
ALTER TABLE provinces
ADD COLUMN IF NOT EXISTS edu_none INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS edu_highschool INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS edu_college INTEGER NOT NULL DEFAULT 0;

-- Create indexes on demographic columns for efficient querying
CREATE INDEX IF NOT EXISTS idx_provinces_pop_children ON provinces(pop_children);
CREATE INDEX IF NOT EXISTS idx_provinces_pop_working ON provinces(pop_working);
CREATE INDEX IF NOT EXISTS idx_provinces_pop_elderly ON provinces(pop_elderly);

-- ============================================================================
-- VALIDATION CONSTRAINTS (OPTIONAL - for future enforcement)
-- ============================================================================

-- Note: We are NOT adding constraints in this migration to allow for safe
-- population distribution before enforcement. Python migration script handles
-- the distribution and ensures sum(age brackets) = old population.
-- Constraints can be added in a future migration after validation.
