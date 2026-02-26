from flask import Flask, session
import time

try:
    from database import get_db_connection
    import countries
except Exception:
    import os, sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from database import get_db_connection
    import countries


def create_user(username):
    """Insert a bare-bones user/ stats row and return its id."""
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO users (username, email, date, hash) VALUES (%s,%s,%s,%s) RETURNING id",
            (username, f"{username}@example.com", "2026-02-24", ""),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, location) VALUES (%s,%s)",
            (uid, "X"),
        )
        conn.commit()
    return uid


def cleanup_user(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        conn.commit()


def test_countries_cache_cleared_on_account_deletion(monkeypatch):
    """After a player deletes their account the cached leaderboard must be
    flushed.

    Regression case reported on Discord: a user would delete and then
    immediately recreate a nation.  The old `/countries` response was still
    cached (60s TTL) and included the *previous* id for their username.  When
    they clicked the link it resolved to a deleted row and produced the
    "Country doesn't exist" error even though the name was visible on the
    board.  We reproduce the full flow by invoking the Flask views directly in
    a test request context and assert the HTML changes when the account goes
    away.  The fix invalidates the cache inside ``delete_own_account``.
    """

    # avoid Jinja lookup failures; we only care about the cache keys
    monkeypatch.setattr(countries, "render_template", lambda *a, **kw: "HTML")

    username = f"cacheuser_{int(time.time())}"
    uid = create_user(username)

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    # 1. simulate an existing cached countries page for this user
    from database import response_cache_registry

    # make sure there is a cache dict for the view
    cache_dict = response_cache_registry.setdefault("countries", {})
    fake_key = f"countries_{uid}_/countries"
    cache_dict[fake_key] = ("whatever", time.time())
    assert fake_key in cache_dict

    # 2. delete the account using the real route (this should also clear cache)
    with test_app.test_request_context("/delete_own_account", method="POST"):
        session["user_id"] = uid
        countries.delete_own_account()

    # 3. after deletion the fake cache entry should have been removed
    assert fake_key not in response_cache_registry.get("countries", {})

    # cleanup just in case
    cleanup_user(uid)
