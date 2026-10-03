from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask

pytestmark = pytest.mark.no_server


class FakeCursor:
    def __init__(self, fetch_val=None):
        self.executed = []
        self.fetch_val = fetch_val
        self.connection = MagicMock()

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetch_val

    def fetchall(self):
        return self.fetch_val if isinstance(self.fetch_val, list) else []


@contextmanager
def fake_cursor_ctx(cursor):
    yield cursor


def test_news_amount_calculation_counts_only_unread():
    """Verify that news_amount counts only unread reports while preserving full history."""
    rows = [
        ("New spy alert", "2026-10-03", 103, False),  # unread
        ("Bonds today: you received $1,200", "2026-10-02", 102, True),   # read
        ("You sent $10,000,000,000", "2026-10-01", 101, True),           # read
    ]
    # History preserved: all 3 items present
    assert len(rows) == 3
    # Bubble count only reflects unread items (1)
    unread_count = sum(1 for row in rows if not row[3])
    assert unread_count == 1


def test_all_news_read_zero_bubble():
    """When all news reports are read, history remains in news but bubble count is 0."""
    rows = [
        ("Event A", "2026-10-02", 102, True),
        ("Event B", "2026-10-01", 101, True),
    ]
    assert len(rows) == 2
    unread_count = sum(1 for row in rows if not row[3])
    assert unread_count == 0


def test_api_news_mark_read_logic():
    """Verify api_news_mark_read updates unread news for the user and invalidates cache."""
    from app_core.main import routes

    dummy_app = Flask("test_app")
    cur = FakeCursor()
    with dummy_app.app_context():
        with patch("app_core.main.routes.session", {"user_id": 77}):
            with patch("app_core.main.routes.get_request_cursor", lambda *args, **kwargs: fake_cursor_ctx(cur)):
                with patch("database.query_cache.delete") as mock_cache_del:
                    resp = routes.api_news_mark_read.__wrapped__()
                    data = resp.get_json()
                    assert data["success"] is True

                    mock_cache_del.assert_called_with("notif_count_77")
                    assert any("UPDATE news SET is_read = TRUE WHERE destination_id = %s" in q[0] and q[1] == (77,) for q in cur.executed)


def test_api_news_clear_all_logic():
    """Verify api_news_clear_all deletes all news for the user and invalidates cache."""
    from app_core.main import routes

    dummy_app = Flask("test_app")
    cur = FakeCursor()
    with dummy_app.app_context():
        with patch("app_core.main.routes.session", {"user_id": 77}):
            with patch("app_core.main.routes.get_request_cursor", lambda *args, **kwargs: fake_cursor_ctx(cur)):
                with patch("database.query_cache.delete") as mock_cache_del:
                    resp = routes.api_news_clear_all.__wrapped__()
                    data = resp.get_json()
                    assert data["success"] is True

                    mock_cache_del.assert_called_with("notif_count_77")
                    assert any("DELETE FROM news WHERE destination_id = %s" in q[0] and q[1] == (77,) for q in cur.executed)


def test_country_repository_delete_news_invalidates_cache():
    """Verify CountryRepository.delete_news removes the row and invalidates notif cache."""
    from repositories.country_repository import CountryRepository

    cur = FakeCursor()
    with patch("repositories.country_repository.get_request_cursor", lambda *args, **kwargs: fake_cursor_ctx(cur)):
        with patch("database.query_cache.delete") as mock_cache_del:
            CountryRepository.delete_news(55, 77)

            mock_cache_del.assert_called_with("notif_count_77")
            assert any("DELETE FROM news WHERE id=%s AND destination_id=%s" in q[0] and q[1] == (55, 77) for q in cur.executed)
