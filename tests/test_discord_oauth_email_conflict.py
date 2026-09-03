"""Regression test for the 2026-09-03 Discord-login account-takeover bug.

Root cause (fixed in commit 165ee659): a plain Discord "login" against
/callback matched an existing account by email alone (LOWER(email) =
LOWER(discord_email)) and auto-logged the visitor into it -- no password,
no confirmation, no prior session. Any Discord identity whose verified
email happened to match an existing user's email (including the pile of
generic placeholder emails like test@test.com still live in prod) could
silently take over that account.

This test drives the real /callback view with the Discord HTTP calls
mocked out, so it exercises the actual production code path rather than
re-describing the fix in prose. It must never touch a live database --
the DB cursor is fully mocked.
"""
from contextlib import contextmanager

import pytest

# Fully self-contained: the Discord HTTP calls and the DB cursor are both
# mocked below, so this doesn't need the live app subprocess other
# integration tests here spin up.
pytestmark = pytest.mark.no_server


def _dummy_cursor_factory(results):
    """Returns a get_request_cursor() replacement.

    Each call to the returned factory hands out a fresh dummy cursor whose
    fetchone() returns the next entry in `results`, matching /callback's
    real query order (duplicate discord_id/hash check first, then the
    email-collision lookup).
    """
    calls = {"i": 0}

    @contextmanager
    def _factory(*_args, **_kwargs):
        idx = calls["i"]
        calls["i"] += 1

        class DummyDB:
            def execute(self, *_a, **_kw):
                return None

            def fetchone(self):
                return results[idx] if idx < len(results) else None

        yield DummyDB()

    return _factory


class _DummyDiscordResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _DummyDiscordSession:
    def __init__(self, payload):
        self._payload = payload

    def fetch_token(self, *_args, **_kwargs):
        return {"access_token": "fake-token"}

    def get(self, _url):
        return _DummyDiscordResponse(self._payload)


def test_discord_login_email_collision_does_not_auto_login(client, monkeypatch):
    """A brand-new Discord identity sharing an existing user's email must
    be sent to prove ownership via password login, never logged straight
    in -- this is the exact scenario that was exploited against Dede's
    account (id 1, email test@test.com) on 2026-09-03."""
    import database
    import signup as signup_module

    discord_payload = {
        "id": "discord-new-identity-12345",
        "email": "collision@example.com",
        "verified": True,
    }

    monkeypatch.setattr(signup_module, "OAUTH2_CLIENT_SECRET", "fake-secret")
    monkeypatch.setattr(
        signup_module,
        "make_session",
        lambda token=None, state=None, scope=None: _DummyDiscordSession(discord_payload),
    )

    # 1st get_request_cursor() call = the discord_id/hash duplicate check
    #   -> no existing discord-linked account (None)
    # 2nd get_request_cursor() call = the email-collision lookup
    #   -> an existing account (id 99) owns this email and isn't linked
    #      to this Discord identity yet
    monkeypatch.setattr(
        database,
        "get_request_cursor",
        _dummy_cursor_factory([None, (99, None)]),
    )
    database._users_column_cache["discord_id"] = True

    with client.session_transaction() as sess:
        sess["oauth2_state"] = "fake-state"
        # no oauth2_intent set -> defaults to plain "login"

    resp = client.get("/callback?state=fake-state&code=fake-code", follow_redirects=True)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "already exists" in body

    with client.session_transaction() as sess:
        assert "user_id" not in sess
