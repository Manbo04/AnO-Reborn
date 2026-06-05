"""Login POST must not 500 on policies edge cases or invalid bcrypt hashes."""


import bcrypt
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app_client():
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


def test_login_post_missing_credentials_returns_400(app_client):
    r = app_client.post("/login/", data={"username": "", "password": ""})
    assert r.status_code == 400


def test_login_post_wrong_user_returns_403(app_client):
    mock_db = MagicMock()
    mock_db.fetchone.return_value = None

    with patch("login.get_request_cursor") as get_cur:
        get_cur.return_value.__enter__.return_value = mock_db
        with patch("login._detect_users_schema", return_value=(False, False)):
            r = app_client.post(
                "/login/",
                data={"username": "nobody", "password": "secret"},
            )
    assert r.status_code == 403


def test_login_post_existing_policies_row_does_not_duplicate_insert(app_client):
    """Regression: SELECT education,soldiers failure must not INSERT duplicate policies."""
    hashed = bcrypt.hashpw(b"secret", bcrypt.gensalt())
    user_row = (16, "Tester", "t@test.com", "", hashed, "normal")
    mock_db = MagicMock()
    mock_db.fetchone.side_effect = [user_row, (1,)]  # user, policies exists

    with patch("login.get_request_cursor") as get_cur:
        get_cur.return_value.__enter__.return_value = mock_db
        with patch("login._detect_users_schema", return_value=(False, False)):
            with patch("login.bcrypt.checkpw", return_value=True):
                r = app_client.post(
                    "/login/",
                    data={"username": "Tester", "password": "secret"},
                )
    assert r.status_code in (302, 200)
    insert_calls = [
        c
        for c in mock_db.execute.call_args_list
        if c[0][0].strip().upper().startswith("INSERT INTO POLICIES")
    ]
    assert insert_calls == []


def test_login_post_invalid_hash_returns_400_not_500(app_client):
    user_row = (16, "Tester", "t@test.com", "", "not-a-bcrypt-hash", "normal")
    mock_db = MagicMock()
    mock_db.fetchone.return_value = user_row

    with patch("login.get_request_cursor") as get_cur:
        get_cur.return_value.__enter__.return_value = mock_db
        with patch("login._detect_users_schema", return_value=(False, False)):
            r = app_client.post(
                "/login/",
                data={"username": "Tester", "password": "secret"},
            )
    assert r.status_code == 400
    assert b"Invalid Server Error" not in r.data


def test_login_post_empty_password_field_returns_403_not_500(app_client):
    user_row = (16, "Tester", "t@test.com", "", None, "normal")
    mock_db = MagicMock()
    mock_db.fetchone.return_value = user_row

    with patch("login.get_request_cursor") as get_cur:
        get_cur.return_value.__enter__.return_value = mock_db
        with patch("login._detect_users_schema", return_value=(False, False)):
            r = app_client.post(
                "/login/",
                data={"username": "Tester", "password": "secret"},
            )
    assert r.status_code == 403
    assert b"Invalid Server Error" not in r.data
