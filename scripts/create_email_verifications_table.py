"""Simple migration script to create `email_verifications` table.

Run locally with: PYTHONPATH=. venv310/bin/python scripts/create_email_verifications_table.py
(This will connect using config.parse_database_url environment variables.)
"""
from database import get_db_connection

SQL = """
CREATE TABLE IF NOT EXISTS email_verifications (
    token TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    user_id INTEGER,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata JSONB
);
"""

if __name__ == "__main__":
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(SQL)
        conn.commit()
        print("✓ email_verifications table created or already exists")
