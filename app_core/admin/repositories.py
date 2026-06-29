import os
import ast
from database import get_request_cursor, get_db_connection

class AdminRepository:
    @staticmethod
    def ensure_admin_tables(db):
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_actions (
                id SERIAL PRIMARY KEY,
                actor INTEGER NOT NULL,
                action TEXT NOT NULL,
                user_id INTEGER,
                details TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_user_controls (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                is_banned BOOLEAN NOT NULL DEFAULT FALSE,
                ban_reason TEXT,
                kick_pending BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_economy_snapshots (
                id SERIAL PRIMARY KEY,
                snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                resource_name TEXT NOT NULL,
                total_quantity BIGINT NOT NULL DEFAULT 0,
                player_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_economy_snapshots_time_resource
            ON game_economy_snapshots (resource_name, snapshot_time DESC)
            """
        )

    @staticmethod
    def log_admin_action(db, actor, action, user_id, details):
        db.execute(
            (
                "INSERT INTO admin_actions (actor, action, user_id, details) "
                "VALUES (%s, %s, %s, %s)"
            ),
            (actor, action, user_id, details),
        )

    @staticmethod
    def validate_target_user(db, target_user_id):
        db.execute("SELECT id, username FROM users WHERE id=%s", (target_user_id,))
        return db.fetchone()

    @staticmethod
    def get_controlled_users(db):
        db.execute(
            """
            SELECT u.id, u.username,
                   COALESCE(c.is_banned, FALSE) AS is_banned,
                   COALESCE(c.kick_pending, FALSE) AS kick_pending,
                   COALESCE(c.ban_reason, '') AS ban_reason
            FROM users u
            LEFT JOIN admin_user_controls c ON c.user_id = u.id
            WHERE COALESCE(c.is_banned, FALSE) = TRUE
               OR COALESCE(c.kick_pending, FALSE) = TRUE
            ORDER BY u.id ASC
            """
        )
        return db.fetchall()

    @staticmethod
    def get_recent_actions(db):
        db.execute(
            """
            SELECT aa.actor,
                   COALESCE(actor_u.username, CAST(aa.actor AS TEXT), 'System') AS actor_name,
                   aa.action,
                   aa.user_id AS target_id,
                   COALESCE(target_u.username, '—') AS target_name,
                   aa.details,
                   aa.created_at
            FROM admin_actions aa
            LEFT JOIN users actor_u
                ON (CAST(aa.actor AS TEXT) ~ '^[0-9]+$' AND actor_u.id = CAST(aa.actor AS INTEGER))
                OR (CAST(aa.actor AS TEXT) !~ '^[0-9]+$' AND actor_u.username = CAST(aa.actor AS TEXT))
            LEFT JOIN users target_u ON target_u.id = aa.user_id
            ORDER BY aa.created_at DESC
            LIMIT 50
            """
        )
        return db.fetchall()

    @staticmethod
    def get_new_accounts_by_day(db):
        db.execute(
            """
            SELECT date, COUNT(*) AS cnt
            FROM users
            WHERE date::date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY date
            ORDER BY date DESC
            """
        )
        return db.fetchall()

    @staticmethod
    def take_economy_snapshot(db):
        AdminRepository.ensure_admin_tables(db)
        db.execute("SELECT COALESCE(SUM(gold), 0), COUNT(*) FROM stats WHERE gold > 0")
        gold_row = db.fetchone()
        db.execute(
            """
            INSERT INTO game_economy_snapshots
                (resource_name, total_quantity, player_count)
            VALUES ('gold', %s, %s)
            """,
            (gold_row[0], gold_row[1]),
        )

        db.execute(
            """
            SELECT rd.name,
                   COALESCE(SUM(ue.quantity), 0),
                   COUNT(*) FILTER (WHERE ue.quantity > 0)
            FROM resource_dictionary rd
            LEFT JOIN user_economy ue ON ue.resource_id = rd.resource_id
            WHERE rd.is_active = TRUE
              AND rd.name != 'money'
            GROUP BY rd.name
            ORDER BY rd.name
            """
        )
        for row in db.fetchall():
            db.execute(
                """
                INSERT INTO game_economy_snapshots
                    (resource_name, total_quantity, player_count)
                VALUES (%s, %s, %s)
                """,
                (row[0], row[1], row[2]),
            )

        db.execute(
            """
            DELETE FROM game_economy_snapshots
            WHERE snapshot_time < NOW() - INTERVAL '90 days'
            """
        )

    @staticmethod
    def get_current_totals(db):
        db.execute(
            """
            SELECT DISTINCT ON (resource_name)
                   resource_name, total_quantity, player_count, snapshot_time
            FROM game_economy_snapshots
            ORDER BY resource_name, snapshot_time DESC
            """
        )
        return db.fetchall()

    @staticmethod
    def get_snapshot_count(db):
        db.execute("SELECT COUNT(*) FROM game_economy_snapshots")
        snap_row = db.fetchone()
        return snap_row[0] if snap_row else 0

    @staticmethod
    def get_snapshot_time_series(db, resource, days):
        db.execute(
            """
            SELECT snapshot_time, total_quantity, player_count
            FROM game_economy_snapshots
            WHERE resource_name = %s
              AND snapshot_time > NOW() - make_interval(days => %s)
            ORDER BY snapshot_time ASC
            """,
            (resource, days),
        )
        return db.fetchall()

    @staticmethod
    def get_resource_id_by_name(db, name):
        db.execute("SELECT resource_id FROM resource_dictionary WHERE name=%s", (name,))
        return db.fetchone()

    @staticmethod
    def get_active_resource_id_by_name(db, name):
        db.execute(
            "SELECT resource_id FROM resource_dictionary WHERE name=%s AND is_active=TRUE",
            (name,)
        )
        return db.fetchone()

    @staticmethod
    def add_gold(db, target_user_id, amount):
        db.execute(
            "UPDATE stats SET gold = gold + %s WHERE id = %s",
            (amount, target_user_id),
        )

    @staticmethod
    def add_resource_quantity(db, target_user_id, resource_id, amount):
        db.execute(
            """
            INSERT INTO user_economy (user_id, resource_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, resource_id)
            DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
            """,
            (target_user_id, resource_id, amount),
        )

    @staticmethod
    def get_max_province_id(db, target_user_id):
        db.execute(
            "SELECT COALESCE(MAX(id), 0) FROM provinces WHERE userId=%s",
            (target_user_id,),
        )
        max_row = db.fetchone()
        return max_row[0] if max_row else 0

    @staticmethod
    def add_province(db, target_user_id, province_name):
        db.execute(
            "INSERT INTO provinces (userId, provinceName, pop_children) "
            "VALUES (%s, %s, 1000000)",
            (target_user_id, province_name),
        )

    @staticmethod
    def set_user_ban_status(db, target_user_id, is_banned, reason=None, kick_pending=False):
        db.execute(
            """
            INSERT INTO admin_user_controls (
                user_id, is_banned, ban_reason, kick_pending, updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET is_banned=EXCLUDED.is_banned,
                          ban_reason=EXCLUDED.ban_reason,
                          kick_pending=EXCLUDED.kick_pending,
                          updated_at=NOW()
            """,
            (target_user_id, is_banned, reason, kick_pending),
        )

    @staticmethod
    def get_db_diagnostics(action=None):
        from psycopg2.extras import RealDictCursor
        out = {}
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            if action == "enable_pg_stat_statements":
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
                conn.commit()
                return {"enabled": True}

            if action and action.startswith("explain_"):
                kind = action.split("explain_", 1)[1]
                if kind == "infra":
                    sql = (
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                        "SELECT ub.user_id, bd.name, ub.quantity "
                        "FROM user_buildings ub "
                        "INNER JOIN building_dictionary bd "
                        "ON ub.building_id = bd.building_id "
                        "ORDER BY ub.user_id ASC LIMIT 500;"
                    )
                elif kind == "stats":
                    sql = (
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                        "SELECT id, gold FROM stats "
                        "ORDER BY id ASC LIMIT 500;"
                    )
                elif kind == "stats_full":
                    sql = (
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                        "SELECT id, gold FROM stats WHERE id IN "
                        "(SELECT id FROM users) LIMIT 10000;"
                    )
                else:
                    return {"error": "unknown explain target"}
                cur.execute(sql)
                return {"result": cur.fetchall()}

            cur.execute("SHOW max_connections;")
            out["max_connections"] = cur.fetchone()

            cur.execute("SELECT count(*) FROM pg_stat_activity;")
            out["active_connections"] = cur.fetchone()

            cur.execute("SELECT state, count(*) FROM pg_stat_activity GROUP BY state;")
            out["states"] = cur.fetchall()

            cur.execute(
                """
                SELECT pid, usename, state, now() - query_start AS duration,
                       left(query, 1000) AS query
                FROM pg_stat_activity
                WHERE state <> 'idle' AND query <> '<IDLE>'
                ORDER BY duration DESC
                LIMIT 20
                """
            )
            long_queries = cur.fetchall()

            import datetime as _dt
            serialized_long = []
            for row in long_queries:
                r = dict(row)
                if isinstance(r.get("duration"), _dt.timedelta):
                    r["duration"] = str(r["duration"])
                if "query" in r and isinstance(r["query"], str):
                    r["query"] = r["query"][:1000]
                serialized_long.append(r)
            out["long_queries"] = serialized_long

            try:
                cur.execute(
                    """
                    SELECT query, calls, total_time, mean_time
                    FROM pg_stat_statements
                    ORDER BY total_time DESC
                    LIMIT 20;
                    """
                )
                out["pg_stat_statements"] = cur.fetchall()
            except Exception:
                out["pg_stat_statements"] = "unavailable"

        def _make_serializable(obj):
            if isinstance(obj, dict):
                return {k: _make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_make_serializable(v) for v in obj]
            if isinstance(obj, (str, int, float, bool)) or obj is None:
                return obj
            return str(obj)

        return _make_serializable(out)

    @staticmethod
    def migrate_treaties():
        conn = get_db_connection()
        db = conn.cursor()
        try:
            db.execute("""
                CREATE TABLE IF NOT EXISTS treaties (
                    id SERIAL PRIMARY KEY,
                    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    treaty_type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(sender_id, recipient_id, treaty_type)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS poll_votes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    poll_name VARCHAR(50) NOT NULL,
                    vote_option VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, poll_name)
                )
            """)
            conn.commit()
            return True, "Treaties and Poll tables migrated successfully!"
        except Exception as e:
            conn.rollback()
            return False, f"Error: {e}"
        finally:
            db.close()
            conn.close()


    @staticmethod
    def get_debug_wealth():
        with get_request_cursor(read_only=True) as db:
            db.execute(
                """
                SELECT resource_id, name, display_name 
                FROM resource_dictionary 
                ORDER BY resource_id;
                """
            )
            return db.fetchall()

    @staticmethod
    def get_live_feed():
        out = {}
        with get_request_cursor() as db:
            db.execute("SELECT id, username, email, date FROM users ORDER BY id DESC LIMIT 20")
            out['users'] = db.fetchall()
            db.execute("SELECT ip_address, attempt_time, successful FROM signup_attempts ORDER BY attempt_time DESC LIMIT 20")
            out['attempts'] = db.fetchall()
            db.execute("SELECT id, destination_id, message, date FROM news ORDER BY id DESC LIMIT 20")
            out['news'] = db.fetchall()
            db.execute("SELECT id, attacker, defender, war_type, peace_date FROM wars ORDER BY id DESC LIMIT 10")
            out['wars'] = db.fetchall()
            db.execute("SELECT u.id, u.username, s.gold FROM users u JOIN stats s ON u.id = s.id ORDER BY s.gold DESC LIMIT 10")
            out['wealth'] = db.fetchall()
            db.execute("SELECT o.offer_id, u.username, o.type, o.resource, o.amount, o.price FROM offers o JOIN users u ON o.user_id = u.id ORDER BY o.offer_id DESC LIMIT 10")
            out['offers'] = db.fetchall()
            db.execute("SELECT t.offer_id, t.type, u1.username, u2.username, t.resource, t.amount, t.price FROM trades t JOIN users u1 ON t.offerer = u1.id JOIN users u2 ON t.offeree = u2.id ORDER BY t.offer_id DESC LIMIT 10")
            out['trades'] = db.fetchall()
        return out

    @staticmethod
    def get_leviathan_debug(wipe_now=False, wipe_provinces=False):
        out = {}
        with get_request_cursor() as db:
            db.execute("SELECT id FROM colNames WHERE name ILIKE '%leviathan%'")
            row = db.fetchone()
            if not row:
                return None, "Leviathan not found"
            colid = row[0]
            
            if wipe_now:
                db.execute("SELECT u.id FROM coalitions_legacy c JOIN users u ON c.userid = u.id WHERE c.colid = %s", (colid,))
                member_ids = [row[0] for row in db.fetchall()]
                if member_ids:
                    db.execute("UPDATE stats SET gold = 100000 WHERE id = ANY(%s)", (member_ids,))
                    db.execute("UPDATE user_economy SET quantity = 0 WHERE user_id = ANY(%s)", (member_ids,))
                db.execute("""
                    UPDATE colBanks SET 
                    money=0, iron=0, coal=0, lumber=0, bauxite=0, oil=0, uranium=0, 
                    lead=0, copper=0, rations=0, steel=0, aluminium=0, gasoline=0, 
                    ammunition=0, consumer_goods=0, components=0 
                    WHERE colId = %s
                """, (colid,))
                
            if wipe_provinces:
                db.execute("SELECT u.id FROM coalitions_legacy c JOIN users u ON c.userid = u.id WHERE c.colid = %s", (colid,))
                member_ids = [row[0] for row in db.fetchall()]
                if member_ids:
                    db.execute("""
                        DELETE FROM provinces 
                        WHERE userid = ANY(%s) 
                        AND id NOT IN (
                            SELECT MIN(id) FROM provinces 
                            WHERE userid = ANY(%s) 
                            GROUP BY userid
                        )
                    """, (member_ids, member_ids))
                    deleted_count = db.rowcount
                    out['wiped_count'] = deleted_count
                
            db.execute("SELECT u.username, s.gold, c.role FROM coalitions_legacy c JOIN users u ON c.userid = u.id JOIN stats s ON u.id = s.id WHERE c.colid = %s ORDER BY s.gold DESC", (colid,))
            out['members'] = db.fetchall()
                
            db.execute("SELECT money, iron, coal, lumber, bauxite, oil, uranium, lead, copper, rations, steel, aluminium, gasoline, ammunition, consumer_goods, components FROM colBanks WHERE colId = %s", (colid,))
            out['bank'] = db.fetchone()
            
            db.execute("SELECT t.offer_id, t.type, u.username, t.resource, t.amount, t.price FROM trades t JOIN users u ON t.offerer = u.id WHERE t.offerer = t.offeree LIMIT 100")
            out['exploits'] = db.fetchall()
            
            db.execute("SELECT actor, action, user_id, details FROM admin_actions ORDER BY created_at DESC LIMIT 20")
            out['admin_logs'] = db.fetchall()
            
            db.execute("SELECT column_name, column_default FROM information_schema.columns WHERE table_name='stats'")
            out['triggers'] = db.fetchall()
        return out, None

    @staticmethod
    def get_exploits_debug(wipe=False):
        out = {}
        with get_request_cursor() as db:
            db.execute("SELECT u.username, s.gold FROM users u JOIN stats s ON u.id = s.id WHERE s.gold > 1000000000 ORDER BY s.gold DESC LIMIT 50")
            out['suspicious_gold'] = db.fetchall()
            
            db.execute("""
                SELECT u.username, rd.name, ue.quantity 
                FROM user_economy ue 
                JOIN users u ON ue.user_id = u.id 
                JOIN resource_dictionary rd ON ue.resource_id = rd.resource_id
                WHERE ue.quantity > 100000000 
                ORDER BY ue.quantity DESC LIMIT 50
            """)
            out['suspicious_resources'] = db.fetchall()
            
            db.execute("SELECT t.offer_id, t.type, u.username, t.resource, t.amount, t.price FROM trades t JOIN users u ON t.offerer = u.id WHERE t.offerer = t.offeree LIMIT 100")
            out['all_self_trades'] = db.fetchall()
            
            db.execute("""
                SELECT cn.name, cb.money, cb.iron, cb.steel, cb.aluminium, cb.gasoline 
                FROM colBanks cb 
                JOIN colNames cn ON cb.colId = cn.id 
                WHERE cb.money > 1000000000 OR cb.steel > 100000000 OR cb.aluminium > 100000000
                ORDER BY cb.money DESC LIMIT 50
            """)
            out['suspicious_banks'] = db.fetchall()

            if wipe:
                if out['suspicious_gold']:
                    db.execute("UPDATE stats SET gold = 100000 WHERE gold > 1000000000")
                if out['suspicious_resources']:
                    db.execute("UPDATE user_economy SET quantity = 0 WHERE quantity > 100000000")
                if out['suspicious_banks']:
                    db.execute("UPDATE colBanks SET money=0, iron=0, coal=0, lumber=0, bauxite=0, oil=0, uranium=0, lead=0, copper=0, rations=0, steel=0, aluminium=0, gasoline=0, ammunition=0, consumer_goods=0, components=0 WHERE money > 1000000000 OR steel > 100000000")
                out['wiped'] = True
        return out
