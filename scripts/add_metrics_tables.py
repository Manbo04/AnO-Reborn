"""Create DB tables for metrics and trade audits.

Run: python scripts/add_metrics_tables.py
"""
from database import get_db_connection

TABLES = [
    (
        "trade_events",
        """
        CREATE TABLE IF NOT EXISTS trade_events (
            id SERIAL PRIMARY KEY,
            offer_id TEXT,
            offerer INTEGER,
            offeree INTEGER,
            resource TEXT,
            amount INTEGER,
            price INTEGER,
            total INTEGER,
            trade_type TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """,
    ),
    (
        "task_metrics",
        """
        CREATE TABLE IF NOT EXISTS task_metrics (
            id SERIAL PRIMARY KEY,
            task_name TEXT,
            duration_seconds DOUBLE PRECISION,
            measured_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """,
    ),
]


def main():
    with get_db_connection() as conn:
        db = conn.cursor()
        for name, ddl in TABLES:
            print(f"Creating table {name}...")
            db.execute(ddl)
    print("Done.")


if __name__ == "__main__":
    main()
