"""Add user reset/deactivation audit columns to `users` table.

Adds:
 - is_active BOOLEAN DEFAULT TRUE
 - reset_required BOOLEAN DEFAULT FALSE
 - reset_at TIMESTAMP WITH TIME ZONE DEFAULT NULL

Run locally (safe to re-run):
PYTHONPATH=. venv310/bin/python scripts/add_user_reset_columns.py
"""

from src.database import get_db_connection

SQL = """
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS reset_required BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reset_at TIMESTAMP WITH TIME ZONE;
"""

if __name__ == "__main__":
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(SQL)
        conn.commit()
        print(
            "✓ users table updated with reset columns "
            "(is_active, reset_required, reset_at)"
        )
