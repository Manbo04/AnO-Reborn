"""Regression tests: error() must use (status_code, message) order."""

import pytest

from app import app
from helpers import error


@pytest.fixture
def app_ctx():
    app.config["TESTING"] = True
    with app.app_context():
        yield app


def test_error_returns_numeric_http_status(app_ctx):
    body, status = error(400, "Bad request")
    assert status == 400
    if hasattr(body, "get_data"):
        assert b"Bad request" in body.get_data()
    else:
        assert "Bad request" in str(body)


def test_error_500_status(app_ctx):
    _body, status = error(500, "Server issue")
    assert status == 500


def test_swapped_error_args_produce_invalid_status(app_ctx):
    """Document the bug: message string is not a valid HTTP status."""
    _body, status = error("Not enough money", 400)
    assert status == "Not enough money"
    assert status != 400


def test_all_templates_compile(app_ctx):
    """Compile templates with the app's Jinja env (includes custom filters)."""
    env = app_ctx.jinja_env
    names = [n for n in env.list_templates() if n.endswith(".html")]
    assert names, "expected HTML templates"
    for name in names:
        env.get_template(name)


def test_signup_missing_password_returns_400(client, monkeypatch):
    """Missing password must not raise AttributeError on .encode()."""

    class _FakeCursor:
        def execute(self, *args, **kwargs):
            pass

        def fetchone(self):
            return (0,)

    class _FakeCM:
        def __enter__(self):
            return _FakeCursor()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("database.get_request_cursor", lambda: _FakeCM())
    monkeypatch.setattr("signup.verify_recaptcha", lambda _r: True)

    resp = client.post(
        "/signup",
        data={
            "username": "nosignup_user_x",
            "email": "nosignup@example.com",
            "confirmation": "x",
            "key": "invalid",
            "continent": "1",
        },
    )
    assert resp.status_code == 400
    assert b"Password and confirmation are required" in resp.data


@pytest.mark.skipif(
    not __import__("os").getenv("PG_DATABASE"),
    reason="DB not configured",
)
def test_province_invalid_unit_returns_400_not_500(client):
    """Invalid building name should return 400, not global 500."""
    with client.session_transaction() as sess:
        sess["user_id"] = 16

    resp = client.post(
        "/buy/not_a_real_building/1",
        data={"not_a_real_building": "1"},
    )
    assert resp.status_code == 400
    assert b"No such unit exists" in resp.data
    assert b"error_code" not in resp.data.lower()


@pytest.mark.skipif(
    not __import__("os").getenv("PG_DATABASE"),
    reason="DB not configured",
)
def test_military_invalid_unit_returns_400_not_500(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 16

    resp = client.post(
        "/military/buy/not_a_real_unit",
        data={"not_a_real_unit": "1"},
    )
    assert resp.status_code == 400
    assert b"No such unit exists" in resp.data
