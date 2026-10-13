"""A route that writes and then answers with an error must not commit the write;
a normal success still commits (teardown_request_connection + after_request)."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.no_server


def _run(status, keep=False, rollback_call=False):
    """Run one fake request through the app's real after_request + teardown hooks.

    No route is registered: Flask forbids add_url_rule once the shared app has
    served a request, so we push a request context and call the hooks directly."""
    from app import app
    from database import get_request_cursor, keep_request_writes, rollback_request

    conn = MagicMock()
    conn.closed = 0

    with patch("database.db_pool.get_connection", return_value=conn), \
         patch("database.db_pool.return_connection"):
        ctx = app.test_request_context("/_rb_test")
        ctx.push()
        try:
            with get_request_cursor() as db:
                db.execute("UPDATE t SET x = 1")
            if keep:
                keep_request_writes()
            if rollback_call:
                rollback_request()
            response = app.make_response(("body", status))
            app.process_response(response)
        finally:
            ctx.pop()  # runs teardown_request_connection
    return conn


def test_error_response_rolls_back():
    conn = _run(403)
    conn.rollback.assert_called()
    conn.commit.assert_not_called()


def test_server_error_response_rolls_back():
    conn = _run(500)
    conn.commit.assert_not_called()


def test_success_commits():
    conn = _run(200)
    conn.commit.assert_called_once()


def test_keep_request_writes_opt_out_commits():
    conn = _run(403, keep=True)
    conn.commit.assert_called_once()


def test_rollback_request_on_redirect_path():
    conn = _run(302, rollback_call=True)
    conn.rollback.assert_called()
    conn.commit.assert_not_called()


def test_bare_app_context_still_commits():
    from app import app
    from database import get_request_cursor

    conn = MagicMock()
    conn.closed = 0
    with patch("database.db_pool.get_connection", return_value=conn), \
         patch("database.db_pool.return_connection"):
        with app.app_context():
            with get_request_cursor() as db:
                db.execute("SELECT 1")
    conn.commit.assert_called_once()
