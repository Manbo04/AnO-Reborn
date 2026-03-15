-- Migration 016: Add tax_rate column to colNames for alliance taxes
-- Tax rate is a percentage (0-20) of gold income collected from members each tick

ALTER TABLE colNames ADD COLUMN IF NOT EXISTS tax_rate INTEGER NOT NULL DEFAULT 0;

-- Constraint to keep tax rate within valid bounds
ALTER TABLE colNames ADD CONSTRAINT chk_tax_rate CHECK (tax_rate >= 0 AND tax_rate <= 20);
