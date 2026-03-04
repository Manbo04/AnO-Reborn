-- Migration 0012: Add join_number column to users table
-- Stores the "early adopter" sequential rank based on account creation order

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS join_number INTEGER UNIQUE;

-- Create index for filtering by join_number
CREATE INDEX IF NOT EXISTS idx_users_join_number ON users(join_number);
