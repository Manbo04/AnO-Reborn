-- Migration: Add game tick execution logs
-- Date: 2026-03-02
-- Purpose: Track global tick start/end, status, and throughput metrics

BEGIN;

CREATE TABLE IF NOT EXISTS game_tick_logs (
    tick_id BIGSERIAL PRIMARY KEY,
    tick_type VARCHAR(40) NOT NULL DEFAULT 'global_tick',
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    finished_at TIMESTAMP WITH TIME ZONE,
    users_processed INTEGER NOT NULL DEFAULT 0,
    production_entries INTEGER NOT NULL DEFAULT 0,
    consumption_entries INTEGER NOT NULL DEFAULT 0,
    total_production BIGINT NOT NULL DEFAULT 0,
    total_consumption BIGINT NOT NULL DEFAULT 0,
    total_deserted_units BIGINT NOT NULL DEFAULT 0,
    error_message TEXT,
    CONSTRAINT game_tick_logs_valid_status CHECK (
        status IN ('running', 'completed', 'failed')
    ),
    CONSTRAINT game_tick_logs_nonnegative_counts CHECK (
        users_processed >= 0
        AND production_entries >= 0
        AND consumption_entries >= 0
        AND total_production >= 0
        AND total_consumption >= 0
        AND total_deserted_units >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_game_tick_logs_started_at
    ON game_tick_logs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_game_tick_logs_status
    ON game_tick_logs(status);

COMMIT;
