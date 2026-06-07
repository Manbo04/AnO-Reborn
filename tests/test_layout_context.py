"""Layout context processor: game_asset_path, admin ids, DB failure resilience."""
from unittest.mock import patch

import pytest


@pytest.fixture
def client():
    from app import app

    with app.test_client() as c:
        yield c


def test_homepage_renders_with_game_ui_context(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Affairs and Order" in r.data or b"affairsandorder" in r.data.lower()


def test_logged_in_render_survives_db_connection_failure(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    with patch("database.get_request_cursor", side_effect=Exception("db down")):
        r = client.get("/login")
    assert r.status_code == 200
