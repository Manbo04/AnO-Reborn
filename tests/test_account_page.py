"""Account page must return 200 for logged-in users."""

import os

import pytest

from app import app

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
)

TEST_USER_ID = 16


@pytest.fixture
def client():
    return app.test_client()


def test_account_page_logged_in(client):
    with client.session_transaction() as sess:
        sess["user_id"] = TEST_USER_ID

    resp = client.get("/account")
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert "Invalid Server Error" not in data
    assert "Account Information" in data


def test_account_redirects_anonymous(client):
    resp = client.get("/account")
    assert resp.status_code in (302, 303)
    assert "/login" in (resp.headers.get("Location") or "")
