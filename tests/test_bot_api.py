"""Tests for Discord bot HTTP API (Phase 1)."""

import os
import uuid

import pytest

from app import app
from bot_api import create_discord_link_code, register_discord_with_code
from database import (
    discord_link_codes_table_exists,
    get_db_connection,
    resolve_user_id_by_discord,
    users_table_has_column,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
)

TEST_USER_ID = 16
BOT_SECRET = "pytest-bot-api-secret"


@pytest.fixture
def bot_api_env(monkeypatch):
    monkeypatch.setenv("BOT_API_SECRET", BOT_SECRET)


@pytest.fixture
def bot_client(bot_api_env):
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def _bot_headers(discord_user_id=None):
    headers = {"X-Bot-Secret": BOT_SECRET}
    if discord_user_id:
        headers["X-Discord-User-Id"] = str(discord_user_id)
    return headers


@pytest.fixture(scope="module", autouse=True)
def _ensure_discord_bot_migration():
    if not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"):
        yield
        return
    if discord_link_codes_table_exists():
        yield
        return
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "0022_discord_bot.sql"
    )
    if not migration.exists():
        pytest.skip("Migration 0022 not found")
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        conn.cursor().execute(migration.read_text())
    finally:
        conn.close()
    yield


def test_bot_api_forbidden_without_secret(bot_client):
    resp = bot_client.get("/api/bot/nation?identifier=16")
    assert resp.status_code == 403


def test_register_and_me_flow(bot_client):
    if not discord_link_codes_table_exists():
        pytest.skip("discord_link_codes table not available")
    if not users_table_has_column("discord_id"):
        pytest.skip("users.discord_id not available")

    fake_discord = f"pytest{uuid.uuid4().hex[:12]}"
    original_discord = None

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT discord_id FROM users WHERE id=%s", (TEST_USER_ID,))
        row = db.fetchone()
        if row:
            original_discord = row[0]

    try:
        code = create_discord_link_code(TEST_USER_ID)
        resp = bot_client.post(
            "/api/bot/register",
            json={"discord_user_id": fake_discord, "code": code},
            headers=_bot_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json().get("user_id") == TEST_USER_ID

        me = bot_client.get(
            "/api/bot/me",
            headers=_bot_headers(fake_discord),
        )
        assert me.status_code == 200
        data = me.get_json()
        assert data.get("id") == TEST_USER_ID
        assert "username" in data
        assert "gold" in data

        ok, msg, uid = register_discord_with_code(fake_discord, code)
        assert not ok
        assert uid is None
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                "UPDATE users SET discord_id=%s WHERE id=%s",
                (original_discord, TEST_USER_ID),
            )
            db.execute(
                "DELETE FROM discord_link_codes WHERE user_id=%s",
                (TEST_USER_ID,),
            )
        assert resolve_user_id_by_discord(fake_discord) is None
