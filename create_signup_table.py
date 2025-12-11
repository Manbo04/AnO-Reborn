#!/usr/bin/env python3
"""
One-off migration: create signup_attempts table if it doesn't exist.
Run with:
  railway run python create_signup_table.py
or locally:
  DATABASE_URL="<url>" python create_signup_table.py
"""
import os
import psycopg2

def main():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print('ERROR: DATABASE_URL not set. Run with: DATABASE_URL="<url>" python create_signup_table.py')
        return 1
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS signup_attempts (
                id SERIAL PRIMARY KEY,
                ip VARCHAR(45) NOT NULL,
                fingerprint TEXT,
                email VARCHAR(255),
                attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                successful BOOLEAN DEFAULT FALSE
            );
        ''')
        conn.commit()
        print('✅ signup_attempts table ensured')
        return 0
    except Exception as e:
        conn.rollback()
        print('✗ Failed to create signup_attempts table:', e)
        return 2
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    raise SystemExit(main())
