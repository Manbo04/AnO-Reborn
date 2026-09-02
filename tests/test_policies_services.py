"""Coverage for app_core/policies beyond the one pre-existing test
(test_country_policies.py, kept in place and updated for the new import
path). get_user_policies() is a real cross-module read API - also imported
directly by countries.py and services/country_service.py - so its caching
behavior and the write path's cache-invalidation-after-commit ordering both
get direct tests here.
"""

import pytest

from database import query_cache
from app_core.policies import repositories
from app_core.policies import services

pytestmark = pytest.mark.no_server


class QueuedCursor:
    def __init__(self, results=()):
        self._results = list(results)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self._results.pop(0) if self._results else None

    def fetchall(self):
        return self._results.pop(0) if self._results else []


# ---------------------------------------------------------------------------
# repositories - pure helpers
# ---------------------------------------------------------------------------

def test_format_policy_flags_marks_selected_indices_true():
    result = repositories.format_policy_flags({"soldiers": [2, 5]}, "soldiers", 7)
    assert result["soldiers2"] is True
    assert result["soldiers5"] is True
    assert result["soldiers1"] is False
    assert result["soldiers7"] is False


def test_format_policy_flags_handles_non_list_iterable():
    # DB can return a tuple/array type here, not always a plain list
    result = repositories.format_policy_flags({"soldiers": (1, 3)}, "soldiers", 3)
    assert result == {"soldiers1": True, "soldiers2": False, "soldiers3": True}


def test_parse_policies_from_form_skips_missing_and_converts_present():
    form = {"soldiers1": "1", "soldiers3": "5"}
    result = repositories.parse_policies_from_form("soldiers", 4, form)
    assert result == [1, 5]


def test_update_user_policies_writes_both_fields_separately():
    db = QueuedCursor()
    repositories.update_user_policies(db, 42, [1, 2], [3])
    assert len(db.calls) == 2
    assert db.calls[0] == ("UPDATE policies SET soldiers=%s WHERE user_id=%s", ([1, 2], 42))
    assert db.calls[1] == ("UPDATE policies SET education=%s WHERE user_id=%s", ([3], 42))


# ---------------------------------------------------------------------------
# services.get_user_policies - caching + NULL handling
# ---------------------------------------------------------------------------

def test_get_user_policies_returns_cached_value_without_touching_db():
    query_cache.set("policies_-1001", {"cached": True}, ttl_seconds=60)
    try:
        db = QueuedCursor([(None, None)])  # would raise if ever consumed
        result = services.get_user_policies(-1001, db=db)
        assert result == {"cached": True}
        assert db.calls == []  # never queried - served straight from cache
    finally:
        query_cache.invalidate("policies_-1001")


def test_get_user_policies_null_db_row_becomes_empty_lists():
    query_cache.invalidate("policies_-1002")
    db = QueuedCursor([None])  # no row for this user yet
    result = services.get_user_policies(-1002, db=db)
    try:
        assert result["soldiers1"] is False
        assert result["education1"] is False
    finally:
        query_cache.invalidate("policies_-1002")


def test_get_user_policies_populates_cache_on_miss():
    query_cache.invalidate("policies_-1003")
    db = QueuedCursor([([2], [1])])
    result = services.get_user_policies(-1003, db=db)
    try:
        assert result["soldiers2"] is True
        assert query_cache.get("policies_-1003") == result
    finally:
        query_cache.invalidate("policies_-1003")


# ---------------------------------------------------------------------------
# services.save_user_policies / invalidate_policies_cache - ordering
# ---------------------------------------------------------------------------

def test_save_user_policies_does_not_invalidate_cache_itself():
    # This is the important ordering guarantee: the write and the cache
    # invalidation are two separate calls precisely so the route can commit
    # the transaction (by exiting the `with get_request_cursor()` block)
    # BEFORE invalidating - never the other way around.
    query_cache.set("policies_-1004", {"stale": True}, ttl_seconds=60)
    try:
        db = QueuedCursor()
        services.save_user_policies(db, -1004, [1], [2])
        assert len(db.calls) == 2  # the writes did happen
        assert query_cache.get("policies_-1004") == {"stale": True}  # still there
    finally:
        query_cache.invalidate("policies_-1004")


def test_invalidate_policies_cache_clears_the_entry():
    query_cache.set("policies_-1005", {"stale": True}, ttl_seconds=60)
    services.invalidate_policies_cache(-1005)
    assert query_cache.get("policies_-1005") is None
