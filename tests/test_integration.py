import pytest
from app import app

@pytest.fixture
def client():
    with app.test_client() as c:
        yield c


def test_login_missing_fields_shows_flash(client):
    resp = client.post('/login', data={})
    assert resp.status_code == 400
    assert b"Please provide both username and password." in resp.data


def test_login_bad_credentials_shows_flash(client):
    resp = client.post('/login', data={'username': 'nosuch', 'password': 'pw'})
    # either 400 or 403 depending on branch
    assert resp.status_code in (400, 403)
    assert b"Wrong username or password" in resp.data


def test_forgot_password_flashes_message_for_nonexistent(client):
    resp = client.post('/request_password_reset', data={'email': 'noone@example.com'}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"If an account exists with that email" in resp.data


def test_reset_password_invalid_code_shows_error(client):
    resp = client.post('/reset_password/invalidcode', data={'password': 'newpass123'})
    assert resp.status_code == 400
    assert b"Invalid or expired reset code" in resp.data or b"Invalid or expired reset code." in resp.data


def test_countries_pagination_preserves_filters(client):
    # Simulate logged-in user
    with client.session_transaction() as sess:
        sess['user_id'] = 1

    resp = client.get('/countries?sort=population&sortway=asc&search=testsearch')
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    # Pagination link should contain the filter params
    assert 'sort=population' in data
    assert 'search=testsearch' in data
