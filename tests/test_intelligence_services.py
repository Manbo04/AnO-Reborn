"""Coverage for app_core/intelligence - the old flat intelligence.py had zero
tests despite containing the espionage combat resolution (random outcomes,
resource reveals, spy losses) and a dynamic-SQL column whitelist. This is the
riskiest of the three repository/service-layer pilots so far, so it gets the
most thorough test treatment: repository SQL/whitelist checks with a queued
fake cursor, plus service-level orchestration tests that monkeypatch the
repository calls to make the "random" combat outcome deterministic.
"""

import time

import pytest

import variables
from app_core.intelligence import repositories
from app_core.intelligence import services

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

def test_get_unit_quantity_defaults_to_zero_when_no_row():
    db = QueuedCursor([None])
    assert repositories.get_unit_quantity(db, 1, "spies") == 0


def test_get_unit_quantity_returns_int():
    db = QueuedCursor([(7,)])
    assert repositories.get_unit_quantity(db, 1, "spies") == 7


def test_decrease_unit_quantity_noop_when_unit_unknown():
    db = QueuedCursor([None])
    repositories.decrease_unit_quantity(db, 1, "not_a_real_unit", 5)
    assert len(db.calls) == 1  # only the SELECT ran, no INSERT/UPDATE


def test_decrease_unit_quantity_inserts_then_updates():
    db = QueuedCursor([(42,)])  # unit_id lookup
    repositories.decrease_unit_quantity(db, 1, "spies", 3)
    assert len(db.calls) == 3
    assert "INSERT INTO user_military" in db.calls[1][0]
    assert "UPDATE user_military" in db.calls[2][0]
    assert db.calls[2][1] == (3, 1, 42)


def test_get_revealed_values_units_branch():
    db = QueuedCursor([[("soldiers", 10), ("tanks", 2)]])
    result = repositories.get_revealed_values(db, 2, ["soldiers", "tanks"], "units")
    assert result == {"soldiers": 10, "tanks": 2}
    assert "user_military" in db.calls[-1][0]


def test_get_revealed_values_resources_branch():
    db = QueuedCursor([[("rations", 500)]])
    result = repositories.get_revealed_values(db, 2, ["rations"], "resources")
    assert result == {"rations": 500}
    assert "user_economy" in db.calls[-1][0]


def test_update_revealed_spyinfo_whitelists_column_names():
    db = QueuedCursor()
    repositories.update_revealed_spyinfo(
        db, 99, ["rations", "'; DROP TABLE users; --"], {"rations": 100}
    )
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "rations" in sql
    assert "DROP TABLE" not in sql
    assert params == (100, 99)


def test_update_revealed_spyinfo_noop_when_nothing_whitelisted():
    db = QueuedCursor()
    repositories.update_revealed_spyinfo(db, 99, ["totally_not_a_resource"], {})
    assert db.calls == []


# ---------------------------------------------------------------------------
# services - pure sorting logic
# ---------------------------------------------------------------------------

def test_sort_spy_reports_updates_date_field_to_latest():
    data = [
        {"spyee": 5, "date": 100, "rations": "1000"},
        {"spyee": 5, "date": 200, "rations": "2000"},
    ]
    result = services.sort_spy_reports(data)
    assert result[5]["date"] == 200


def test_sort_spy_reports_field_after_date_keeps_stale_value():
    # Pre-existing quirk in the original code, preserved as-is: it mutates
    # fully_sorted[user]["date"] while iterating a single entry's fields in
    # dict order, so once "date" itself is updated to the new entry's date,
    # any field that comes AFTER "date" in that same entry's key order no
    # longer sees date > fully_sorted[user]["date"] as true and is never
    # updated - it silently keeps the older entry's value. Fields before
    # "date" in key order (like "spyee" here) aren't affected. This isn't
    # "correct" combat-report behavior, but changing it is a behavior
    # change out of scope for a structural migration - this test exists to
    # make sure nobody accidentally "fixes" it in a later refactor without
    # deciding to on purpose.
    data = [
        {"spyee": 5, "date": 100, "rations": "1000"},
        {"spyee": 5, "date": 200, "rations": "2000"},
    ]
    result = services.sort_spy_reports(data)
    assert result[5]["rations"] == "1000"


def test_sort_spy_reports_fills_missing_fields_with_question_mark():
    data = [{"spyee": 5, "date": 100, "rations": "1000"}]
    result = services.sort_spy_reports(data)
    assert result[5]["oil"] == "?"
    assert result[5]["soldiers"] == "?"


def test_fetch_spy_reports_converts_dictrow_style_rows(monkeypatch):
    monkeypatch.setattr(
        services, "get_spy_reports_for_user", lambda db, cId: [{"spyee": 1}, {"spyee": 2}]
    )
    assert services.fetch_spy_reports(None, 1) == [{"spyee": 1}, {"spyee": 2}]


# ---------------------------------------------------------------------------
# services.get_spy_amount_form_data
# ---------------------------------------------------------------------------

def test_get_spy_amount_form_data(monkeypatch):
    monkeypatch.setattr(services, "get_username", lambda db, cId: "Nationia")
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, cId, unit: 7)
    country, spies = services.get_spy_amount_form_data(None, 1)
    assert country == "Nationia"
    assert spies == 7


def test_get_spy_amount_form_data_blank_username_defaults_to_empty_string(monkeypatch):
    monkeypatch.setattr(services, "get_username", lambda db, cId: None)
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, cId, unit: 0)
    country, _ = services.get_spy_amount_form_data(None, 1)
    assert country == ""


# ---------------------------------------------------------------------------
# services.resolve_spy_operation
# ---------------------------------------------------------------------------

def test_resolve_spy_operation_blocks_new_target_during_cooldown(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: (999, time.time()))
    ok, code, msg = services.resolve_spy_operation(None, 1, 2, 5, "resources")
    assert ok is False
    assert code == 400
    assert "cooldown" in msg.lower()


def test_resolve_spy_operation_rejects_non_positive_spies(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    # actual_spies is fetched before the spies<=0 check even runs (matches
    # the original's query order exactly), so this needs a stub too.
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: 5)
    ok, code, msg = services.resolve_spy_operation(None, 1, 2, 0, "resources")
    assert ok is False
    assert msg == "Must send at least 1 spy."


def test_resolve_spy_operation_rejects_insufficient_spies(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: 3)
    ok, code, msg = services.resolve_spy_operation(None, 1, 2, 5, "resources")
    assert ok is False
    assert "don't have enough" in msg


def test_resolve_spy_operation_insert_failure_returns_500(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: 100)
    monkeypatch.setattr(services, "insert_spy_operation", lambda db, cId, eId, ts: None)
    ok, code, msg = services.resolve_spy_operation(None, 1, 2, 5, "resources")
    assert ok is False
    assert code == 500


def test_resolve_spy_operation_own_side_dominant_reveals_with_no_losses(monkeypatch):
    # own_rand == enemy_rand (randomness neutralized) but spies=100 >> enemy_spies=1,
    # so multiplier = enemy_score/own_score = enemy_spies/spies <= 1 for every
    # object => "own wins" every time, and never > 10 => no spies executed.
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    unit_quantities = {1: 100, 2: 1}
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: unit_quantities[uid])
    monkeypatch.setattr(services, "insert_spy_operation", lambda db, cId, eId, ts: 777)
    monkeypatch.setattr(services.rand, "uniform", lambda a, b: 0.5)

    revealed_calls = []
    update_calls = []
    monkeypatch.setattr(
        services,
        "get_revealed_values",
        lambda db, eId, objs, st: revealed_calls.append((eId, list(objs), st)) or {o: 42 for o in objs},
    )
    monkeypatch.setattr(
        services,
        "update_revealed_spyinfo",
        lambda db, opid, objs, revealed: update_calls.append((opid, list(objs), revealed)),
    )
    decrease_calls = []
    monkeypatch.setattr(
        services, "decrease_unit_quantity", lambda db, uid, unit, amt: decrease_calls.append((uid, unit, amt))
    )

    ok, code, msg = services.resolve_spy_operation(None, 1, 2, 100, "resources")

    assert (ok, code) == (True, 200)
    assert revealed_calls, "get_revealed_values should have been called"
    assert revealed_calls[0][0] == 2  # eId
    assert set(revealed_calls[0][1]) == set(variables.RESOURCES)
    assert update_calls and update_calls[0][0] == 777
    assert decrease_calls == [(1, "spies", 0)]


def test_resolve_spy_operation_enemy_dominant_no_reveal_and_spy_lost(monkeypatch):
    # own_rand == enemy_rand, but enemy_spies=1000 >> spies=1, so the first
    # processed object gets multiplier >> 10 => that spy gets executed
    # immediately, which then stops any further objects being processed
    # (spies - executed_spies hits 0) - and "enemy won" means nothing gets
    # revealed for that object either.
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    unit_quantities = {1: 1, 2: 1000}
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: unit_quantities[uid])
    monkeypatch.setattr(services, "insert_spy_operation", lambda db, cId, eId, ts: 888)
    monkeypatch.setattr(services.rand, "uniform", lambda a, b: 0.5)

    monkeypatch.setattr(
        services,
        "get_revealed_values",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    monkeypatch.setattr(
        services,
        "update_revealed_spyinfo",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    decrease_calls = []
    monkeypatch.setattr(
        services, "decrease_unit_quantity", lambda db, uid, unit, amt: decrease_calls.append(amt)
    )

    ok, code, msg = services.resolve_spy_operation(None, 1, 2, 1, "units")

    assert ok is True
    assert decrease_calls == [1]
