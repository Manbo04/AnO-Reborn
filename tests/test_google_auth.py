"""Google OAuth configuration helpers."""
import os

from app_core.auth.google_auth import get_google_redirect_uri, is_google_auth_configured


def test_is_google_auth_configured_false_when_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert is_google_auth_configured() is False


def test_is_google_auth_configured_true_when_both_set(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    assert is_google_auth_configured() is True


def test_redirect_uri_explicit_override(monkeypatch):
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://example.test/callback")
    monkeypatch.delenv("RAILWAY_STATIC_URL", raising=False)
    assert get_google_redirect_uri() == "https://example.test/callback"


def test_redirect_uri_railway_default(monkeypatch):
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    assert get_google_redirect_uri() == "https://affairsandorder.com/login/google/callback"
