"""Regression tests for /login/email column mapping."""

from app_core.auth.passwords import password_matches

def test_password_matches_werkzeug_hash():
    from werkzeug.security import generate_password_hash

    stored = generate_password_hash("secret123")
    assert password_matches(stored, "secret123")
    assert not password_matches(stored, "wrong")


def test_password_matches_rejects_boolean_is_verified():
    """is_verified=True must not be treated as a password hash (was causing 500)."""
    assert not password_matches(True, "secret123")
    assert not password_matches(False, "secret123")
