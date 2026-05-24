"""Request cursor rolls back aborted transactions after SQL errors."""

from unittest.mock import MagicMock, patch

import psycopg2


def test_get_request_cursor_rolls_back_after_sql_error():
    from database import get_request_cursor, rollback_db_cursor

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.connection = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.side_effect = [
        psycopg2.errors.UndefinedColumn("column does not exist"),
    ]

    with patch("database.get_request_connection", return_value=mock_conn):
        try:
            with get_request_cursor() as db:
                db.execute("SELECT bad_col FROM users")
        except psycopg2.Error:
            pass

    mock_conn.rollback.assert_called()
