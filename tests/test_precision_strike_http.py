"""Precision-strike button, news, chosen amount, and disruption on Postgres.

Throwaway users only. Skips unless DATABASE_URL points at a local database.
"""

import os
import time
import uuid

import pytest

from tests._db_cleanup import purge_users

pytestmark = pytest.mark.no_server

needs_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL"),
    reason="needs a local DATABASE_URL and no DATABASE_PUBLIC_URL",
)


def _mk_user(db, tag):
    name = f"strikehttp_{tag}_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, '2026-10-26', 'x', 'normal') RETURNING id",
        (name, f"{name}@example.com"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', 0)",
        (uid,),
    )
    return uid, name


def _give(db, uid, unit, qty):
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT %s, unit_id, %s FROM unit_dictionary WHERE name = %s "
        "ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity = EXCLUDED.quantity",
        (uid, qty, unit),
    )


def _client(uid):
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return client


@needs_db
def test_strike_button_amount_news_and_disruption():
    from database import get_db_connection
    from wars.precision import consume_suppression

    ids = []
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            attacker, _name = _mk_user(db, "a")
            defender, _dname = _mk_user(db, "d")
            ids = [attacker, defender]
            now = time.time()
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, "
                "start_date, last_visited) VALUES (%s, %s, 'Sustained', 'x', %s, %s) "
                "RETURNING id",
                (attacker, defender, now, now),
            )
            war_id = db.fetchone()[0]
            _give(db, attacker, "cruisers", 20)
            _give(db, attacker, "bombers", 10)
            _give(db, defender, "tanks", 500)
            _give(db, defender, "soldiers", 1000)
            conn.commit()

        client = _client(attacker)
        missing = client.post(
            f"/war/{war_id}/attack",
            data={
                "action": "precision_strike",
                "striker": "cruisers",
                "target_unit": "tanks",
            },
        )
        assert missing.status_code == 200
        assert b"Choose how many" in missing.data

        sent = client.post(
            f"/war/{war_id}/attack",
            data={
                "action": "precision_strike",
                "striker": "cruisers",
                "target_unit": "tanks",
                "strike_amount": "4",
            },
            follow_redirects=True,
        )
        assert sent.status_code == 200
        assert b"Precision strike with 4 cruisers" in sent.data
        assert b"with 20 cruisers" not in sent.data

        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "SELECT quantity FROM user_military um "
                "JOIN unit_dictionary ud ON ud.unit_id = um.unit_id "
                "WHERE um.user_id = %s AND ud.name = 'cruisers'",
                (attacker,),
            )
            cruisers_left = db.fetchone()[0]
            db.execute(
                "SELECT quantity FROM user_military um "
                "JOIN unit_dictionary ud ON ud.unit_id = um.unit_id "
                "WHERE um.user_id = %s AND ud.name = 'tanks'",
                (defender,),
            )
            tanks_left = db.fetchone()[0]
            db.execute(
                "SELECT message FROM news WHERE destination_id = %s",
                (defender,),
            )
            news = [row[0] for row in db.fetchall()]
            db.execute(
                "SELECT consumed, target_unit FROM precision_strikes WHERE war_id = %s",
                (war_id,),
            )
            strike_rows = db.fetchall()
            assert cruisers_left >= 16  # sent 4, losses are a small share of those 4
            assert cruisers_left <= 20
            assert tanks_left < 500
            assert any("hit your tanks" in m for m in news)
            assert strike_rows and strike_rows[0][0] is False

            held = consume_suppression(db, war_id, attacker, {"soldiers": 1000})
            assert held == {}
            db.execute(
                "SELECT consumed FROM precision_strikes WHERE war_id = %s",
                (war_id,),
            )
            assert db.fetchone()[0] is False

            spent = consume_suppression(
                db, war_id, attacker, {"tanks": 500, "soldiers": 1000}
            )
            assert "tanks" in spent
            assert 0 < spent["tanks"] <= 0.20
            db.execute(
                "SELECT consumed FROM precision_strikes WHERE war_id = %s",
                (war_id,),
            )
            assert db.fetchone()[0] is True
            conn.commit()

        from wars.bomber_commit import record_sortie

        with get_db_connection() as conn:
            db = conn.cursor()
            record_sortie(db, war_id, attacker, "support", 10)
            conn.commit()
        locked = client.post(
            f"/war/{war_id}/attack",
            data={
                "action": "precision_strike",
                "striker": "bombers",
                "target_unit": "tanks",
                "strike_amount": "1",
            },
        )
        assert locked.status_code == 200
        assert b"free this hour" in locked.data
    finally:
        if not ids:
            return
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "DELETE FROM precision_strikes WHERE attacker_id = ANY(%s) OR target_id = ANY(%s)",
                (ids, ids),
            )
            db.execute(
                "DELETE FROM bomber_sorties WHERE user_id = ANY(%s)",
                (ids,),
            )
            db.execute("DELETE FROM news WHERE destination_id = ANY(%s)", (ids,))
            db.execute(
                "DELETE FROM wars WHERE attacker = ANY(%s) OR defender = ANY(%s)",
                (ids, ids),
            )
            purge_users(db, ids)
            conn.commit()
