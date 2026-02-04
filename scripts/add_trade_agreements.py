#!/usr/bin/env python3
"""Migration: Create trade_agreements table for auto/recurring trades

Run: python scripts/add_trade_agreements.py

Trade Agreements allow two players to set up automatic recurring trades:
- Player A offers X of resource_a
- Player B offers Y of resource_b (or money)
- Trade executes automatically at the specified interval
- Either party can cancel at any time
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection  # noqa: E402

if __name__ == "__main__":
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            print("Creating trade_agreements table...")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_agreements (
                    id SERIAL PRIMARY KEY,

                    -- Proposer (creates the agreement)
                    proposer_id INTEGER NOT NULL,
                    proposer_resource TEXT NOT NULL,
                    proposer_amount INTEGER NOT NULL,

                    -- Receiver (accepts/rejects the agreement)
                    receiver_id INTEGER NOT NULL,
                    receiver_resource TEXT NOT NULL,
                    receiver_amount INTEGER NOT NULL,

                    -- Scheduling
                    interval_hours INTEGER NOT NULL DEFAULT 24,
                    next_execution TIMESTAMP WITH TIME ZONE,
                    last_execution TIMESTAMP WITH TIME ZONE,

                    -- Limits
                    max_executions INTEGER DEFAULT NULL,  -- NULL = unlimited
                    execution_count INTEGER DEFAULT 0,

                    -- Status: pending, active, paused, cancelled, completed, failed
                    status TEXT DEFAULT 'pending',

                    -- Tracking
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

                    -- Optional message/note
                    message TEXT
                );
                """
            )

            print("Creating indexes...")
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trade_agreements_proposer
                ON trade_agreements(proposer_id);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trade_agreements_receiver
                ON trade_agreements(receiver_id);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trade_agreements_status
                ON trade_agreements(status);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trade_agreements_next_exec
                ON trade_agreements(next_execution)
                WHERE status = 'active';
                """
            )

            conn.commit()
            print("✓ Migration complete - trade_agreements table created")
        except Exception as e:
            conn.rollback()
            print("✗ Migration failed:", e)
            raise
        finally:
            cur.close()
