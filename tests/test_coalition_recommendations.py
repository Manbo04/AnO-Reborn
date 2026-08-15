from app import app
from services.country_service import CountryService
from database import get_db_cursor
import pytest
import os


def _db_reachable() -> bool:
    """Return True only if a live DB connection can be established.
    Used by the skip marker so the test is skipped when Railway is down,
    not just when the env var is unset."""
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=5)
        conn.close()
        return True
    except Exception:
        return False


_DB_AVAILABLE = _db_reachable()

pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE,
    reason="Requires a reachable Postgres (DATABASE_PUBLIC_URL or DATABASE_URL not set or server unreachable)",
)


def test_coalition_recommendations_solo_player():
    with get_db_cursor() as db:
        # Create a test user
        db.execute(
            "INSERT INTO users (username, email, hash, date, auth_type) "
            "VALUES ('test_rec_user', 'test_rec@example.invalid', 'hash', '1970-01-01', 'normal') "
            "RETURNING id"
        )
        user_id = db.fetchone()[0]

        db.execute("INSERT INTO stats (id, location) VALUES (%s, 'Tundra')", (user_id,))

        # Create two recruiting coalitions and one non-recruiting
        db.execute(
            "INSERT INTO colNames (name, type, recruiting, description, date) "
            "VALUES ('Recruiting Col 1', 'Open', true, 'Recruiting 1 desc', '1970-01-01') RETURNING id"
        )
        col1_id = db.fetchone()[0]

        db.execute(
            "INSERT INTO colNames (name, type, recruiting, description, date) "
            "VALUES ('Recruiting Col 2', 'Invite Only', true, 'Recruiting 2 desc', '1970-01-01') RETURNING id"
        )
        col2_id = db.fetchone()[0]

        db.execute(
            "INSERT INTO colNames (name, type, recruiting, description, date) "
            "VALUES ('Closed Col', 'Open', false, 'Not recruiting', '1970-01-01') RETURNING id"
        )
        col3_id = db.fetchone()[0]

        db.connection.commit()

        try:
            with app.app_context():
                # Fetch profile for user_id, with session_user_id = user_id (viewer is owner)
                profile = CountryService.get_country_profile(user_id, user_id)
                assert "recommended_coalitions" in profile
                recs = profile["recommended_coalitions"]
                # Should recommend the 2 recruiting coalitions, but not the closed one
                rec_ids = [r["id"] for r in recs]
                assert col1_id in rec_ids
                assert col2_id in rec_ids
                assert col3_id not in rec_ids

                # Now put the user in a coalition and verify recommended_coalitions is empty/not returned
                db.execute(
                    "INSERT INTO coalitions_legacy (colid, userid, role) VALUES (%s, %s, 'member')",
                    (col1_id, user_id)
                )
                # Update the users table coalition_id
                db.execute("UPDATE users SET coalition_id = %s WHERE id = %s", (col1_id, user_id))
                db.connection.commit()

                profile_joined = CountryService.get_country_profile(user_id, user_id)
                assert not profile_joined.get("recommended_coalitions")

        finally:
            # Clean up
            db.execute("DELETE FROM coalitions_legacy WHERE userid = %s", (user_id,))
            db.execute("DELETE FROM stats WHERE id = %s", (user_id,))
            db.execute("DELETE FROM users WHERE id = %s", (user_id,))
            db.execute("DELETE FROM colNames WHERE id IN (%s, %s, %s)", (col1_id, col2_id, col3_id))
            db.connection.commit()
