"""Regression test: a logged-in player's session cookie must never ride on a
publicly cacheable response.

Found 2026-09-23, fresh adversarial pass on the account cross-contamination
investigation (see memory: ano-account-cross-contamination-recurrence-2026-09-22
and app_core/auth/session_interface.py for the full mechanism write-up).

Every login path in this app sets session.permanent = True, and Flask's
SESSION_REFRESH_EACH_REQUEST defaults to True (never overridden here), so
Flask re-issues the player's real signed session cookie on EVERY response --
including /static/*.css|.js, which app.py's after_request marks
`Cache-Control: public, max-age=3600`. after_request handlers run BEFORE the
session interface, so the bytes that went out on the wire were:

    Cache-Control: public, max-age=3600, must-revalidate
    Set-Cookie: session=<a real, valid, signed session for one live player>

Any shared cache in the path (Cloudflare, a carrier or corporate proxy) is
explicitly invited to store that and replay it to every later visitor, who
then silently becomes that player with zero credentials entered. `Vary: Cookie`
is not a defense -- Cloudflare documents that it ignores Vary except for
Accept-Encoding.

Verified before the fix by driving the REAL app (not a mock): a logged-in
test client GETting /static/style.css got back both headers above, with a
decodable session cookie carrying the player's own user_id.
"""

import pytest
from flask import Flask, Response, session

from app_core.auth.session_interface import PublicCacheSafeSessionInterface


SESSION_COOKIE_NAME = "session"


def _session_cookies(response):
    """Set-Cookie headers that actually carry a session value (not a delete)."""
    out = []
    for raw in response.headers.getlist("Set-Cookie"):
        if not raw.startswith(f"{SESSION_COOKIE_NAME}="):
            continue
        value = raw.split("=", 1)[1].split(";", 1)[0]
        if value:
            out.append(raw)
    return out


def _make_app(session_interface):
    app = Flask(__name__)
    app.secret_key = "test-secret-not-real-2026-09-23"
    if session_interface is not None:
        app.session_interface = session_interface

    @app.route("/asset")
    def asset():
        # Stands in for /static/*.css|.js -- and for the flag / ad /
        # province-image / social-card views, whose own `public` headers are
        # currently overwritten by app.py's after_request but would become
        # live the moment that ordering changed.
        return Response("body", mimetype="text/css")

    @app.route("/page")
    def page():
        return Response("<html></html>", mimetype="text/html")

    @app.route("/logout_on_asset")
    def logout_on_asset():
        session.clear()
        return Response("body", mimetype="text/css")

    @app.after_request
    def _cache_headers(response):
        # Mirrors app.py's own after_request, which runs BEFORE the session
        # interface -- that ordering is the whole point of the bug.
        if response.mimetype == "text/css":
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        else:
            response.headers["Cache-Control"] = "private, max-age=5, must-revalidate"
        return response

    return app


def _login(client, user_id):
    """Exactly what every real login path in this app does."""
    with client.session_transaction() as sess:
        sess.permanent = True
        sess["user_id"] = user_id


@pytest.mark.parametrize("path", ["/asset"])
def test_public_response_carries_no_session_cookie(path):
    app = _make_app(PublicCacheSafeSessionInterface())
    client = app.test_client()
    _login(client, 4242)

    response = client.get(path)

    assert response.status_code == 200
    assert "public" in response.headers["Cache-Control"]
    leaked = _session_cookies(response)
    assert not leaked, (
        "a publicly cacheable response carried a live session cookie -- any "
        f"shared cache may replay it to every later visitor: {leaked}"
    )


def test_private_response_still_refreshes_the_session_cookie():
    """The fix must not break Flask's normal rolling-expiry refresh."""
    app = _make_app(PublicCacheSafeSessionInterface())
    client = app.test_client()
    _login(client, 4242)

    response = client.get("/page")

    assert "private" in response.headers["Cache-Control"]
    assert _session_cookies(response), (
        "normal (private) responses must still re-issue the session cookie, "
        "or permanent sessions stop rolling forward"
    )


def test_clearing_the_session_on_a_public_route_still_revokes_the_cookie():
    """Logout/ban/kick must still reach the browser -- and must not be cached."""
    app = _make_app(PublicCacheSafeSessionInterface())
    client = app.test_client()
    _login(client, 4242)

    response = client.get("/logout_on_asset")

    cookie_headers = response.headers.getlist("Set-Cookie")
    assert any(
        h.startswith(f"{SESSION_COOKIE_NAME}=;") or f"{SESSION_COOKIE_NAME}=; " in h
        for h in cookie_headers
    ), f"session revocation never reached the browser: {cookie_headers}"
    assert "no-store" in response.headers["Cache-Control"], (
        "a revocation cookie was left on a publicly cacheable response -- a "
        "shared cache replaying it would log out every later visitor"
    )


def test_stock_flask_is_vulnerable_without_the_fix():
    """Pins the actual pre-fix behaviour, so this test can't silently pass
    because Flask changed rather than because the fix is in place."""
    app = _make_app(None)  # stock SecureCookieSessionInterface
    client = app.test_client()
    _login(client, 4242)

    response = client.get("/asset")

    assert "public" in response.headers["Cache-Control"]
    assert _session_cookies(response), (
        "stock Flask no longer puts a session cookie on this response -- the "
        "bug this test guards against may have moved; re-verify by hand"
    )
