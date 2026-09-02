"""Coverage for app_core/upgrades. The one pre-existing test for this module
(test_upgrades_integration.py) turned out to be stale - it tests a resource-
deduction code path that predates the tech/research system and is now marked
skip with an explanation. This file covers the actual current behavior:
get_upgrades()'s legacy-key/tech-name mapping and caching, and the
upgrades_sb dedup lookup for duplicate tech_dictionary rows.
"""

import pytest

from database import query_cache
from app_core.upgrades import repositories
from app_core.upgrades import services

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
# repositories
# ---------------------------------------------------------------------------

def test_legacy_and_tech_maps_are_inverses():
    for legacy_key, tech_name in repositories.LEGACY_UPGRADE_TO_TECH.items():
        assert repositories.TECH_TO_LEGACY_UPGRADE[tech_name] == legacy_key


def test_get_active_tech_id_by_name_prefers_active_row():
    db = QueuedCursor([(77,)])
    tech_id = repositories.get_active_tech_id_by_name(db, "cheaper_materials")
    assert tech_id == 77
    sql, params = db.calls[-1]
    assert "is_active DESC" in sql
    assert params == ("cheaper_materials",)


def test_get_active_tech_id_by_name_missing_returns_none():
    db = QueuedCursor([None])
    assert repositories.get_active_tech_id_by_name(db, "not_a_real_tech") is None


# ---------------------------------------------------------------------------
# services.get_upgrades - cross-module public API
# ---------------------------------------------------------------------------

def test_get_upgrades_returns_cached_value_without_touching_db():
    query_cache.set("upgrades_-2001", {"cached": True}, ttl_seconds=60)
    try:
        db = QueuedCursor([[("cheaper_materials",)]])  # would be consumed if hit
        result = services.get_upgrades(-2001, db=db)
        assert result == {"cached": True}
        assert db.calls == []
    finally:
        query_cache.invalidate("upgrades_-2001")


def test_get_upgrades_maps_unlocked_tech_names_to_legacy_keys():
    query_cache.invalidate("upgrades_-2002")
    db = QueuedCursor([[("cheaper_materials",), ("looting_teams",)]])
    result = services.get_upgrades(-2002, db=db)
    try:
        assert result["cheapermaterials"] is True
        assert result["lootingteams"] is True
        assert result["icbmsilo"] is False  # not unlocked
    finally:
        query_cache.invalidate("upgrades_-2002")


def test_get_upgrades_all_false_when_nothing_unlocked():
    query_cache.invalidate("upgrades_-2003")
    db = QueuedCursor([[]])
    result = services.get_upgrades(-2003, db=db)
    try:
        assert all(v is False for v in result.values())
        assert set(result.keys()) == set(repositories.LEGACY_UPGRADE_TO_TECH.keys())
    finally:
        query_cache.invalidate("upgrades_-2003")


def test_get_upgrades_populates_cache_on_miss():
    query_cache.invalidate("upgrades_-2004")
    db = QueuedCursor([[("cheaper_materials",)]])
    result = services.get_upgrades(-2004, db=db)
    try:
        assert query_cache.get("upgrades_-2004") == result
    finally:
        query_cache.invalidate("upgrades_-2004")


# ---------------------------------------------------------------------------
# services.build_upgrades_page_data
# ---------------------------------------------------------------------------

def test_build_upgrades_page_data_shapes_costs_and_prereqs():
    # tech_id, display_name, research_cost, prerequisite_tech_id, name, description
    tech_rows = [
        (1, "Cheaper Materials", "5000", None, "cheaper_materials", "desc"),
        (2, "Looting Teams", "9000", 1, "looting_teams", "desc"),
        (3, "Something Unmapped", "1000", None, "not_a_legacy_upgrade", "desc"),
    ]
    db = QueuedCursor([tech_rows, [(1,)]])  # catalog query, then unlocked-ids query
    result_rows, unlocked_ids, tech_costs, tech_prereq_names = services.build_upgrades_page_data(db, 5)

    assert result_rows == tech_rows
    assert unlocked_ids == {1}
    assert tech_costs["cheapermaterials"] == 5000
    assert tech_costs["lootingteams"] == 9000
    assert set(tech_costs.keys()) == {"cheapermaterials", "lootingteams"}  # unmapped tech skipped
    assert tech_prereq_names["lootingteams"] == "Cheaper Materials"
    assert "cheapermaterials" not in tech_prereq_names  # no prerequisite


def test_build_upgrades_page_data_unknown_prereq_id_gets_fallback_label():
    tech_rows = [
        (2, "Looting Teams", "9000", 999, "looting_teams", "desc"),  # prereq 999 not in catalog
    ]
    db = QueuedCursor([tech_rows, []])  # catalog query, then empty unlocked-ids query
    _, _, _, tech_prereq_names = services.build_upgrades_page_data(db, 5)
    assert tech_prereq_names["lootingteams"] == "an earlier technology"


# ---------------------------------------------------------------------------
# services.invalidate_upgrade_caches
# ---------------------------------------------------------------------------

def test_invalidate_upgrade_caches_clears_the_upgrades_cache():
    query_cache.set("upgrades_-2005", {"stale": True}, ttl_seconds=60)
    services.invalidate_upgrade_caches(-2005)
    assert query_cache.get("upgrades_-2005") is None


def test_invalidate_upgrade_caches_swallows_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("cache backend down")

    monkeypatch.setattr("database.invalidate_user_cache", boom)
    # should not raise
    services.invalidate_upgrade_caches(-2006)
