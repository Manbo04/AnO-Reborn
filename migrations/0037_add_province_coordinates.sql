-- Migration: Add X and Y coordinates to provinces for the Hex Map

ALTER TABLE provinces ADD COLUMN coordinate_x INTEGER;
ALTER TABLE provinces ADD COLUMN coordinate_y INTEGER;

-- Ensure no two provinces can occupy the exact same tile
CREATE UNIQUE INDEX IF NOT EXISTS idx_province_coordinates ON provinces(coordinate_x, coordinate_y) WHERE coordinate_x IS NOT NULL AND coordinate_y IS NOT NULL;
