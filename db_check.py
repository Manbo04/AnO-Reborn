from database import get_db_connection
with get_db_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT u.id, u.username, COALESCE(ue.quantity, 0) as total_money
            FROM users u
            JOIN user_economy ue ON u.id = ue.user_id
            JOIN resource_dictionary rd ON ue.resource_id = rd.resource_id
            WHERE rd.name = 'money'
            LIMIT 5
        """)
        print("Without verified:", cur.fetchall())

        cur.execute("""
            SELECT u.id, u.username, COALESCE(ue.quantity, 0) as total_money
            FROM users u
            JOIN user_economy ue ON u.id = ue.user_id
            JOIN resource_dictionary rd ON ue.resource_id = rd.resource_id
            WHERE u.is_verified = TRUE AND rd.name = 'money'
            LIMIT 5
        """)
        print("With verified:", cur.fetchall())
