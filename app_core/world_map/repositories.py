from database import get_request_cursor

class WorldMapRepository:
    @staticmethod
    def get_user_coalition(user_id):
        with get_request_cursor(read_only=True) as db:
            db.execute(
                """
                SELECT c.id, c.name 
                FROM colNames c
                JOIN coalitions_legacy m ON c.id = m.colid
                WHERE m.userid = %s
                """, (user_id,)
            )
            return db.fetchone()

    @staticmethod
    def get_nodes():
        with get_request_cursor(read_only=True) as db:
            db.execute(
                """
                SELECT 
                    n.id, n.name, n.type, n.coordinate_x, n.coordinate_y, 
                    n.controlling_coalition_id, c.name as coalition_name,
                    n.health, n.shield_expires_at, n.tier
                FROM nodes n
                LEFT JOIN colNames c ON n.controlling_coalition_id = c.id
                """
            )
            return db.fetchall()

    @staticmethod
    def get_user_stats_for_update(user_id):
        with get_request_cursor() as db:
            db.execute("SELECT gold FROM stats WHERE id = %s FOR UPDATE", (user_id,))
            return db.fetchone()

    @staticmethod
    def get_user_military_for_update(user_id):
        with get_request_cursor() as db:
            db.execute("SELECT soldiers FROM military WHERE id = %s FOR UPDATE", (user_id,))
            return db.fetchone()

    @staticmethod
    def get_node_for_update(node_id):
        with get_request_cursor() as db:
            db.execute("SELECT name, controlling_coalition_id, shield_expires_at, COALESCE(tier, 1) as tier FROM nodes WHERE id = %s FOR UPDATE", (node_id,))
            return db.fetchone()

    @staticmethod
    def apply_capture(user_id, node_id, coalition_id, cost_gold, cost_soldiers, shield_hours):
        with get_request_cursor() as db:
            db.execute("UPDATE stats SET gold = gold - %s WHERE id = %s", (cost_gold, user_id))
            db.execute("UPDATE military SET soldiers = soldiers - %s WHERE id = %s", (cost_soldiers, user_id))
            db.execute(
                "UPDATE nodes SET controlling_coalition_id = %s, shield_expires_at = CURRENT_TIMESTAMP + %s * INTERVAL '1 hour' WHERE id = %s",
                (coalition_id, shield_hours, node_id)
            )
