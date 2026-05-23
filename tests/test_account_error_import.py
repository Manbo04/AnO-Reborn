"""Regression: account route must import helpers.error (404 path)."""

from helpers import error


def test_error_helper_returns_tuple():
    resp = error(404, "not found")
    assert resp[1] == 404
