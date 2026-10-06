"""The REAL app rejects state-changing POSTs without a CSRF token.

Other tests turn CSRF off on their test client / test server so they can drive
forms directly; this one keeps it on to prove production behaviour.
"""
import pytest


@pytest.mark.no_server
@pytest.mark.parametrize("path", ["/login", "/signup", "/account/request_password_reset"])
def test_post_without_csrf_token_is_rejected(path):
    from app import app

    old_enabled = app.config.get("WTF_CSRF_ENABLED", True)
    old_testing = app.config.get("TESTING", False)
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["TESTING"] = False
    try:
        with app.test_client() as client:
            resp = client.post(path, data={"username": "x", "password": "y"})
        assert resp.status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = old_enabled
        app.config["TESTING"] = old_testing
