"""Create helpful indexes to improve query performance.

Run this script manually once (or as part of migrations) against the production
database to add indexes used by frequent WHERE clauses. Uses "CREATE INDEX IF
NOT EXISTS" so it is safe to run multiple times.

Make sure you have DB credentials in the environment (as used by
`database.get_db_connection`).
"""

from database import get_db_connection

INDEXES = [
    # Typical lookup patterns
    ("provinces_userid_idx", "provinces", "userId"),
    ("offers_user_id_idx", "offers", "user_id"),
    ("offers_resource_idx", "offers", "resource"),
    ("offers_price_idx", "offers", "price"),
    ("coalitions_userid_idx", "coalitions", "userId"),
    ("trades_offer_id_idx", "trades", "offer_id"),
    ("wars_attacker_defender_idx", "wars", "attacker, defender"),
]


def main():
    with get_db_connection() as conn:
        cur = conn.cursor()
        for idx_name, table, columns in INDEXES:
            sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns})"
            print("Executing:", sql)
            cur.execute(sql)
        conn.commit()
        print("Indexes ensured.")


if __name__ == "__main__":
    main()
