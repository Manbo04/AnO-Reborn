"""Regression test for the hourly economy-snapshot connection leak.

task_economy_snapshot (tasks.py) runs get_request_cursor() inside a bare
`with app.app_context():` block -- there's no real HTTP request, so
app.teardown_request() never fires. Before this fix, the pooled connection
checked out via get_request_connection() was never returned, leaking one
connection per hourly run until DB_MAX_CONNECTIONS was exhausted.

app.py now also registers teardown_request_connection on
app.teardown_appcontext, which must release the connection when a bare
app context (no request) is popped.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.no_server


def test_bare_app_context_releases_request_scoped_connection():
    from app import app
    from database import get_request_cursor

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("database.db_pool.get_connection", return_value=mock_conn) as mock_get, \
         patch("database.db_pool.return_connection") as mock_return:
        with app.app_context():
            with get_request_cursor() as db:
                db.execute("SELECT 1")

        # Context is popped -- teardown_appcontext should have fired and
        # returned the connection to the pool exactly once.
        mock_get.assert_called_once()
        mock_return.assert_called_once()
        returned_conn = mock_return.call_args[0][0]
        assert returned_conn is mock_conn


def test_real_request_teardown_still_only_releases_once():
    """Guard against the double-registration (teardown_request +
    teardown_appcontext) double-releasing a connection on a real request."""
    from app import app
    from database import get_request_cursor

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("database.db_pool.get_connection", return_value=mock_conn), \
         patch("database.db_pool.return_connection") as mock_return:
        with app.test_request_context("/"):
            with get_request_cursor() as db:
                db.execute("SELECT 1")

        assert mock_return.call_count == 1
