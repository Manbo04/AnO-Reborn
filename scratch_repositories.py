def get_repos_code():
    return """import os
import ast
from database import get_request_cursor, get_db_connection

class AdminRepository:
    @staticmethod
    def ensure_admin_tables(db):
        db.execute(
            \"\"\"
            CREATE TABLE IF NOT EXISTS admin_actions (
                id SERIAL PRIMARY KEY,
                actor INTEGER NOT NULL,
                action TEXT NOT NULL,
                user_id INTEGER,
                details TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            \"\"\"
        )
        db.execute(
            \"\"\"
            CREATE TABLE IF NOT EXISTS admin_user_controls (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                is_banned BOOLEAN NOT NULL DEFAULT FALSE,
                ban_reason TEXT,
                kick_pending BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            \"\"\"
        )
        db.execute(
            \"\"\"
            CREATE TABLE IF NOT EXISTS game_economy_snapshots (
                id SERIAL PRIMARY KEY,
                snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                resource_name TEXT NOT NULL,
                total_quantity BIGINT NOT NULL DEFAULT 0,
                player_count INTEGER NOT NULL DEFAULT 0
            )
            \"\"\"
        )
        db.execute(
            \"\"\"
            CREATE INDEX IF NOT EXISTS idx_economy_snapshots_time_resource
            ON game_economy_snapshots (resource_name, snapshot_time DESC)
            \"\"\"
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
            \"\"\"
            SELECT u.id, u.username,
                   COALESCE(c.is_banned, FALSE) AS is_banned,
                   COALESCE(c.kick_pending, FALSE) AS kick_pending,
                   COALESCE(c.ban_reason, '') AS ban_reason
            FROM users u
            LEFT JOIN admin_user_controls c ON c.user_id = u.id
            WHERE COALESCE(c.is_banned, FALSE) = TRUE
               OR COALESCE(c.kick_pending, FALSE) = TRUE
            ORDER BY u.id ASC
            \"\"\"
        )
        return db.fetchall()

    @staticmethod
    def get_recent_actions(db):
        db.execute(
            \"\"\"
            SELECT aa.actor,
                   COALESCE(actor_u.username, aa.actor, 'System') AS actor_name,
                   aa.action,
                   aa.user_id AS target_id,
                   COALESCE(target_u.username, '—') AS target_name,
                   aa.details,
                   aa.created_at
            FROM admin_actions aa
            LEFT JOIN users actor_u
                ON (aa.actor ~ '^[0-9]+$' AND actor_u.id = aa.actor::integer)
                OR (aa.actor !~ '^[0-9]+$' AND actor_u.username = aa.actor)
            LEFT JOIN users target_u ON target_u.id = aa.user_id
            ORDER BY aa.created_at DESC
            LIMIT 50
            \"\"\"
        )
        return db.fetchall()

    @staticmethod
    def get_new_accounts_by_day(db):
        db.execute(
            \"\"\"
            SELECT date, COUNT(*) AS cnt
            FROM users
            WHERE date::date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY date
            ORDER BY date DESC
            \"\"\"
        )
        return db.fetchall()
"""

with open('app_core/admin/repositories.py', 'w') as f:
    f.write(get_repos_code())
