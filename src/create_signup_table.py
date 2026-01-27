#!/usr/bin/env python3
"""
One-off migration: create `signup_attempts` table if it doesn't exist.

Usage:
  # Run inside Railway container / environment where DATABASE_URL is set
  railway run python create_signup_table.py

  # Or provide DATABASE_URL locally
  DATABASE_URL="<url>" python create_signup_table.py
"""

import os
import logging
import psycopg2


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logging.getLogger(__name__).error(
            'ERROR: DATABASE_URL not set. Run with: DATABASE_URL="<url>" python create_signup_table.py'
        )
        return 1

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    try:
        # Use column names expected by `signup.py`: ip_address and attempt_time
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS signup_attempts (
                id SERIAL PRIMARY KEY,
                ip_address VARCHAR(45) NOT NULL,
                fingerprint TEXT,
                email VARCHAR(255),
                attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                successful BOOLEAN DEFAULT FALSE
            );
        """
        )
        # Also guard against older tables missing columns by adding them if absent
        cur.execute(
            "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);"
        )
        cur.execute(
            "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS fingerprint TEXT;"
        )
        cur.execute(
            "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS email VARCHAR(255);"
        )
        cur.execute(
            "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
        )
        cur.execute(
            "ALTER TABLE signup_attempts ADD COLUMN IF NOT EXISTS successful BOOLEAN DEFAULT FALSE;"
        )

        conn.commit()
        logging.getLogger(__name__).info(
            "signup_attempts table ensured (columns added if missing)"
        )
        return 0
    except Exception as e:
        conn.rollback()
        logging.getLogger(__name__).exception("Failed to create signup_attempts table")
        return 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
