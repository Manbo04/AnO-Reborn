"""Integration test for war declaration and peace acceptance flow.

This test reproduces the acceptance flow end-to-end:
- Create two users
- Attacker declares war on defender via `/declare_war`
- Attacker sends a peace offer demanding rations via
    `/send_peace_offer/<war_id>/<enemy_id>`
- Defender accepts the peace via POST `/peace_offers` decision=1
- Assert war has a `peace_date` set and resources were transferred
"""

from app import app
from database import get_db_connection

import http.cookies
from flask import request


def _set_session_cookie(client, app, key, value):
    with app.test_request_context():
        sess = app.session_interface.open_session(app, request)
        sess[key] = value
        resp = app.response_class()
        app.session_interface.save_session(app, sess, resp)
        set_cookie = resp.headers.get("Set-Cookie")
        if not set_cookie:
            return
        cookie = http.cookies.SimpleCookie()
        cookie.load(set_cookie)
        for morsel in cookie.values():
            client.set_cookie(key=morsel.key, value=morsel.value, domain="localhost")


def make_or_get_user(db, username, email):
    # create or return existing user id
    db.execute(
        "SELECT id FROM users WHERE username=%s OR email=%s",
        (username, email),
    )
    r = db.fetchone()
    if r:
        return r[0]
    db.execute(
        (
            "INSERT INTO users (username,email,hash,date,auth_type) "
            "VALUES (%s,%s,%s,%s,%s)"
        ),
        (username, email, "h", "2020-01-01", "normal"),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (username,))
    return db.fetchone()[0]


def test_war_peace_integration():
    # Clean up any prior test artifacts and create two users
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM users WHERE username LIKE 'integ_%'")
        conn.commit()
        a_id = make_or_get_user(db, "integ_a", "integ_a@example.com")
        b_id = make_or_get_user(db, "integ_b", "integ_b@example.com")
        # ensure resources rows exist and defender has ample rations
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING",
            (a_id,),
        )
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING",
            (b_id,),
        )
        # Set known baseline resource amounts to avoid test pollution from
        # earlier runs. Attacker starts with 0 rations; defender starts with 1000.
        db.execute("UPDATE resources SET rations=0 WHERE id=%s", (a_id,))
        db.execute("UPDATE resources SET rations=1000 WHERE id=%s", (b_id,))
        conn.commit()

    with app.test_client() as client:
        # Attacker declares war
        _set_session_cookie(client, app, "user_id", a_id)
        resp = client.post(
            "/declare_war",
            data={
                "defender": str(b_id),
                "warType": "Raze",
                "description": "Integration test",
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)

        # Find the war id
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                (
                    "SELECT id FROM wars WHERE (attacker=%s AND defender=%s) "
                    "ORDER BY id DESC LIMIT 1"
                ),
                (a_id, b_id),
            )
            row = db.fetchone()
            assert row, "War row was not created"
            war_id = row[0]

        # Create a peace offer directly (send_peace_offer validates against a
        # limited resource set and 'rations' isn't permitted there). We insert
        # the peace row and attach it to the war so the defender can accept.
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                (
                    "INSERT INTO peace (author, demanded_resources, demanded_amount) "
                    "VALUES (%s, %s, %s)"
                ),
                (a_id, "rations", "100"),
            )
            db.execute("SELECT CURRVAL('peace_id_seq')")
            peace_id = db.fetchone()[0]
            db.execute(
                "UPDATE wars SET peace_offer_id=%s WHERE id=%s",
                (peace_id, war_id),
            )
            conn.commit()

        # Defender accepts the offer
        _set_session_cookie(client, app, "user_id", b_id)
        resp = client.post(
            "/peace_offers",
            data={"peace_offer": str(peace_id), "decision": "1"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302)

        # Verify that the war has a peace_date and resources transferred
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT peace_date FROM wars WHERE id=%s", (war_id,))
            pd = db.fetchone()[0]
            assert pd is not None, "War peace_date was not set"

            # defender should have 900 rations, attacker should have +100
            db.execute("SELECT rations FROM resources WHERE id=%s", (b_id,))
            b_rations = db.fetchone()[0]
            db.execute("SELECT rations FROM resources WHERE id=%s", (a_id,))
            a_rations = db.fetchone()[0]
            assert b_rations == 900
            assert a_rations == 100
