"""A request that writes and then answers with an error status must not commit.

Before: teardown_request_connection committed unconditionally, so any route
that wrote and then ``return error(...)`` persisted the half-applied write.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app import app
from database import (
    get_db_cursor,
    get_request_cursor,
    keep_request_writes_on_error,
    teardown_request_connection,
)

needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
)

TABLE = "zz_request_rollback_scratch"


@pytest.fixture
def scratch():
    with get_db_cursor() as db:
        db.execute(f"DROP TABLE IF EXISTS {TABLE}")
        db.execute(f"CREATE TABLE {TABLE} (v TEXT)")
    yield
    with get_db_cursor() as db:
        db.execute(f"DROP TABLE IF EXISTS {TABLE}")


def _count():
    with get_db_cursor() as db:
        db.execute(f"SELECT COUNT(*) FROM {TABLE}")
        return db.fetchone()[0]


def _run_request(status, keep=False):
    """Write a row in a request context, finish with `status`, tear down."""
    with app.test_request_context("/"):
        with get_request_cursor() as db:
            db.execute(f"INSERT INTO {TABLE} (v) VALUES ('x')")
        if keep:
            keep_request_writes_on_error()
        app.process_response(app.make_response(("body", status)))
        teardown_request_connection(None)


@needs_db
def test_error_response_rolls_back_write(scratch):
    _run_request(400)
    assert _count() == 0


@needs_db
def test_server_error_response_rolls_back_write(scratch):
    _run_request(500)
    assert _count() == 0


@needs_db
def test_success_response_commits_write(scratch):
    _run_request(200)
    assert _count() == 1


@needs_db
def test_redirect_response_commits_write(scratch):
    _run_request(302)
    assert _count() == 1


@needs_db
def test_keep_request_writes_on_error_opts_out(scratch):
    _run_request(403, keep=True)
    assert _count() == 1


def test_teardown_rolls_back_when_flag_set_and_commits_otherwise():
    for flag, expect_commit in ((True, False), (False, True)):
        conn = MagicMock()
        with patch("database.db_pool") as pool, app.test_request_context("/"):
            from flask import g

            g._db_conn = conn
            g._db_rollback = flag
            teardown_request_connection(None)
        assert conn.commit.called is expect_commit
        assert conn.rollback.called is (not expect_commit)
        pool.return_connection.assert_called_once()


def test_flag_does_not_leak_to_next_request():
    conn = MagicMock()
    with patch("database.db_pool"), app.test_request_context("/"):
        from flask import g

        g._db_conn = conn
        g._db_rollback = True
        teardown_request_connection(None)
        assert g._db_rollback is False


def test_commit_failure_is_logged(caplog):
    conn = MagicMock()
    conn.commit.side_effect = RuntimeError("boom")
    with patch("database.db_pool"), app.test_request_context("/"):
        from flask import g

        g._db_conn = conn
        with caplog.at_level("ERROR"):
            teardown_request_connection(None)
    assert "request commit failed" in caplog.text
