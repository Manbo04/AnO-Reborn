"""Migration script to add email verification columns to `users` table.

Adds:
 - is_verified BOOLEAN DEFAULT FALSE
 - verification_token TEXT
 - token_created_at TIMESTAMP WITH TIME ZONE

Run locally (safe to re-run):
PYTHONPATH=. venv310/bin/python scripts/add_verification_user_columns.py
"""

from src.database import get_db_connection

SQL = """
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS verification_token TEXT,
    ADD COLUMN IF NOT EXISTS token_created_at TIMESTAMP WITH TIME ZONE;
"""

if __name__ == "__main__":
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(SQL)
        conn.commit()
        print(
            "✓ users table updated with verification columns "
            "(is_verified, verification_token, token_created_at)"
        )
