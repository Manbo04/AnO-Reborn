"""Discord bot link code: active code lookup and TTL."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from bot_api import CODE_TTL_MINUTES, get_active_discord_link_code


def test_code_ttl_default_is_thirty_minutes():
    assert CODE_TTL_MINUTES >= 30


def test_get_active_discord_link_code_returns_none_when_table_missing():
    with patch("bot_api.discord_link_codes_table_exists", return_value=False):
        assert get_active_discord_link_code(16) is None


def test_get_active_discord_link_code_returns_row():
    exp = datetime.now(timezone.utc) + timedelta(minutes=20)
    db = MagicMock()
    db.fetchone.return_value = ("ABCD1234", exp)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    with patch("bot_api.discord_link_codes_table_exists", return_value=True):
        with patch("database.get_db_cursor", return_value=cm):
            result = get_active_discord_link_code(42)
    assert result["code"] == "ABCD1234"
    assert result["expires_at"] == exp
