"""Country page must return 200 for public and owner views."""

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


def test_country_page_anonymous(client):
    resp = client.get(f"/country/id={TEST_USER_ID}")
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert "500" not in data[:200] or "Invalid Server Error" not in data


def test_country_page_owner_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = TEST_USER_ID

    resp = client.get(f"/country/id={TEST_USER_ID}")
    assert resp.status_code == 200


def test_country_page_not_found(client):
    resp = client.get("/country/id=999999999")
    assert resp.status_code == 404
