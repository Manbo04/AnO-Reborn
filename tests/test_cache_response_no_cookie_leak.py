"""Regression test for a real, likely load-bearing bug in the account
cross-contamination investigation, found live 2026-09-23 while manually
tracing the actual installed Flask/Werkzeug library source at Dede's
explicit direction ("scan code and services until you find the mistake
... don't stop until you find something").

database.py's cache_response() decorator used to cache and hand back the
literal Response object a view returned. For a view returning a real,
mutable Werkzeug Response (jsonify()/make_response() -- as opposed to a
plain string/tuple, which Flask always rebuilds fresh regardless of
caching), every cache hit returned that SAME object instance.

Flask's own session-cookie-refresh logic
(SecureCookieSessionInterface.save_session, part of Flask itself) calls
response.set_cookie() on whatever object a view "returns" on every
request from a logged-in user, because every login path in this app sets
session.permanent = True and SESSION_REFRESH_EACH_REQUEST defaults to
True (confirmed: never overridden anywhere in this app). Werkzeug's
set_cookie() appends to the Set-Cookie header (headers.add(), confirmed
against the installed werkzeug 3.1.6 source) rather than replacing it.

For a public=True cache_response view -- shared across ALL users, not
scoped by user id -- this meant a single cached response object could
accumulate multiple different users' valid signed session cookies over
its cache lifetime, all sent out together to whoever's request next hit
that cache entry. This is a real, concrete, mechanically-verified
candidate mechanism for players getting logged into each other's
accounts, and it explains the reported pattern (needs concurrent real
traffic; can affect multiple different people at once) far better than
anything found by load-testing alone this session.

Fixed by never storing or returning the literal response object: the
decorator now snapshots the body/status/headers into the cache and always
constructs a brand-new Response from that snapshot on every return path,
so Flask's post-processing can only ever mutate a private, single-use
object.

This test uses a minimal standalone Flask app (same style as
tests/test_csrf.py) importing the real cache_response() decorator, with
two separate test clients (separate cookie jars) simulating two already
logged-in users hitting the same public=True endpoint within the cache
TTL window -- and inspects the RAW Set-Cookie headers of the second
user's response for the first user's actual signed cookie value.
"""
from flask import Flask, jsonify, session

from database import cache_response


def _make_app():
    app = Flask(__name__)
    app.secret_key = "test-secret-not-real-2026-09-23"
    app.config["TESTING"] = True

    @app.route("/public_ticker")
    @cache_response(ttl_seconds=30, public=True)
    def public_ticker():
        return jsonify({"ok": True})

    return app


def _login_as(client, marker):
    """Simulate an already-authenticated session the same way every real
    login path in this app does: session.permanent = True, plus some
    session content so each user's signed cookie value is distinct."""
    with client.session_transaction() as sess:
        sess.permanent = True
        sess["user_id"] = marker


def test_public_cache_hit_does_not_leak_other_users_cookie():
    app = _make_app()

    client_a = app.test_client()
    client_b = app.test_client()

    _login_as(client_a, "user-A-12345")
    _login_as(client_b, "user-B-67890")

    # Client A hits first -- populates the shared public cache entry.
    resp_a = client_a.get("/public_ticker")
    assert resp_a.status_code == 200
    cookies_a = resp_a.headers.getlist("Set-Cookie")
    assert len(cookies_a) == 1, f"expected exactly one Set-Cookie for A, got {cookies_a}"
    session_cookie_a = cookies_a[0]

    # Client B hits the SAME public endpoint within the TTL window --
    # this must be a cache hit (same cache key, since public=True ignores
    # user identity), reusing whatever object was cached for A above.
    resp_b = client_b.get("/public_ticker")
    assert resp_b.status_code == 200
    cookies_b = resp_b.headers.getlist("Set-Cookie")

    assert len(cookies_b) == 1, (
        f"client B's response carried {len(cookies_b)} Set-Cookie headers, "
        f"expected exactly 1 -- extra headers on a shared cached response "
        f"mean another user's cookie accumulated on the same object: "
        f"{cookies_b}"
    )
    assert cookies_b[0] != session_cookie_a, (
        "client B's own response never got its own Set-Cookie -- it just "
        "received client A's leftover value"
    )
    assert session_cookie_a not in cookies_b, (
        f"client A's session cookie value leaked into client B's response: "
        f"{cookies_b}"
    )

    # A third hit, back on client A -- must still see nothing but A's own
    # cookie, proving the shared cache entry itself was never mutated by
    # B's request either (not just a lucky "last write wins" outcome).
    resp_a2 = client_a.get("/public_ticker")
    cookies_a2 = resp_a2.headers.getlist("Set-Cookie")
    assert len(cookies_a2) == 1, (
        f"client A's later response carried {len(cookies_a2)} Set-Cookie "
        f"headers, expected exactly 1: {cookies_a2}"
    )
