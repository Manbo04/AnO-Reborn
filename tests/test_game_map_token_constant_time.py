"""Regression test for a real hardening gap found live 2026-09-23 while
auditing app_core/game_map/ during the account cross-contamination
investigation (unrelated to that bug, but in the same "secret token gates
access" family as this file's already-fixed 09-13 GAME_MAP_TOKEN default
issue).

game_map_auth() compared the URL token to GAME_MAP_TOKEN with a plain `==`,
not hmac.compare_digest -- a non-constant-time comparison that leaks how
many leading characters of a guess are correct via response timing. Every
other secret-token comparison in this codebase (admin/guards.py,
market/routes.py's wipe secrets) already uses compare_digest for exactly
this reason. Fixed to match.

This test verifies the functional behavior is unchanged (correct token
still grants access, wrong token is still rejected with 404) and that the
route now genuinely calls hmac.compare_digest rather than `==` -- a timing
side-channel itself isn't something a deterministic unit test can reliably
detect, so this checks the actual comparison call instead.
"""
from unittest.mock import patch

from flask import Flask


def _make_app(token_value):
    import app_core.game_map.routes as game_map_routes

    app = Flask(__name__)
    app.secret_key = "test-secret-not-real"
    app.config["TESTING"] = True
    app.register_blueprint(game_map_routes.bp)
    game_map_routes.GAME_MAP_TOKEN = token_value
    return app, game_map_routes


def test_correct_token_still_grants_access():
    app, _ = _make_app("real-secret-token-abc123")
    client = app.test_client()
    resp = client.get("/game_map/real-secret-token-abc123", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/game_map"
    with client.session_transaction() as sess:
        assert sess.get("game_map_authorized") is True


def test_wrong_token_is_still_rejected():
    app, _ = _make_app("real-secret-token-abc123")
    client = app.test_client()
    resp = client.get("/game_map/wrong-guess", follow_redirects=False)
    assert resp.status_code == 404
    with client.session_transaction() as sess:
        assert not sess.get("game_map_authorized")


def test_comparison_uses_compare_digest_not_plain_equality():
    app, game_map_routes = _make_app("real-secret-token-abc123")
    client = app.test_client()

    with patch.object(
        game_map_routes.hmac, "compare_digest", wraps=game_map_routes.hmac.compare_digest
    ) as spy:
        client.get("/game_map/some-guess", follow_redirects=False)
        assert spy.called, (
            "game_map_auth() did not call hmac.compare_digest -- the token "
            "comparison is not constant-time"
        )
