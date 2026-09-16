"""Coverage for app_core/intelligence - the old flat intelligence.py had zero
tests despite containing the espionage combat resolution (random outcomes,
resource reveals, spy losses) and a dynamic-SQL column whitelist. This is the
riskiest of the three repository/service-layer pilots so far, so it gets the
most thorough test treatment: repository SQL/whitelist checks with a queued
fake cursor, plus service-level orchestration tests that monkeypatch the
repository calls to make the "random" combat outcome deterministic.
"""

import re
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


def test_has_active_embassy_true_when_row_found():
    db = QueuedCursor([(1,)])
    assert repositories.has_active_embassy(db, 1, 2) is True
    sql, params = db.calls[-1]
    assert "treaty_type = 'embassy'" in sql
    assert params == (1, 2, 2, 1)


def test_has_active_embassy_false_when_no_row():
    db = QueuedCursor([None])
    assert repositories.has_active_embassy(db, 1, 2) is False


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
#
# NOTE: resolve_spy_operation() opens with `db.execute("SELECT
# pg_advisory_xact_lock(%s)", ...)` (added 2026-09-13, commit ce27a009, the
# double-spend race sweep) -- every test below passes a QueuedCursor() (a
# no-op-execute stub) instead of raw `None` for `db` so that call doesn't
# blow up with AttributeError before the monkeypatched functions ever run.
# ---------------------------------------------------------------------------

def test_resolve_spy_operation_blocks_new_target_during_cooldown(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: (999, time.time()))
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 5, "resources")
    assert ok is False
    assert code == 400
    assert "cooldown" in msg.lower()


def test_resolve_spy_operation_blocks_same_target_during_cooldown(monkeypatch):
    # 2026-09-16: the cooldown used to only fire on a *different* target
    # (`str(spyee) != str(eId)`), so two nations in a running spy war never
    # hit it -- reported on Discord by a player spying the same rival
    # multiple times an hour. Now it applies regardless of target.
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: (2, time.time()))
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 5, "resources")
    assert ok is False
    assert code == 400
    assert "cooldown" in msg.lower()


def test_resolve_spy_operation_cooldown_message_shows_time_remaining_not_elapsed(monkeypatch):
    # secs_left used to be computed as `current_time - date` (time already
    # elapsed since the last op), not the actual time left before the
    # cooldown clears -- backwards. A player spied 1 hour ago should see
    # ~11 hours left, not ~1 hour.
    one_hour_ago = time.time() - 3600
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: (2, one_hour_ago))
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 5, "resources")
    assert ok is False
    secs_left = int(re.search(r"(\d+) seconds left", msg).group(1))
    expected_remaining = services.SPY_COOLDOWN_SECONDS - 3600
    assert abs(secs_left - expected_remaining) < 5


def test_resolve_spy_operation_rejects_non_positive_spies(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "has_active_embassy", lambda db, cId, eId: False)
    # actual_spies is fetched before the spies<=0 check even runs (matches
    # the original's query order exactly), so this needs a stub too.
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: 5)
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 0, "resources")
    assert ok is False
    assert msg == "Must send at least 1 spy."


def test_resolve_spy_operation_rejects_insufficient_spies(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "has_active_embassy", lambda db, cId, eId: False)
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: 3)
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 5, "resources")
    assert ok is False
    assert "don't have enough" in msg


def test_resolve_spy_operation_blocked_by_active_embassy(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "has_active_embassy", lambda db, cId, eId: True)
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 5, "resources")
    assert ok is False
    assert code == 403
    assert "Embassy" in msg


def test_resolve_spy_operation_insert_failure_returns_500(monkeypatch):
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "has_active_embassy", lambda db, cId, eId: False)
    monkeypatch.setattr(services, "get_unit_quantity", lambda db, uid, unit: 100)
    monkeypatch.setattr(services, "insert_spy_operation", lambda db, cId, eId, ts: None)
    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 5, "resources")
    assert ok is False
    assert code == 500


def test_resolve_spy_operation_own_side_dominant_reveals_with_no_losses(monkeypatch):
    # own_rand == enemy_rand (randomness neutralized) but spies=100 >> enemy_spies=1,
    # so multiplier = enemy_score/own_score = enemy_spies/spies <= 1 for every
    # object => "own wins" every time, and never > 10 => no spies executed.
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "has_active_embassy", lambda db, cId, eId: False)
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

    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 100, "resources")

    assert (ok, code) == (True, 200)
    assert revealed_calls, "get_revealed_values should have been called"
    assert revealed_calls[0][0] == 2  # eId
    assert set(revealed_calls[0][1]) == set(variables.RESOURCES)
    assert update_calls and update_calls[0][0] == 777
    assert decrease_calls == [(1, "spies", 0)]
    assert entry is not None


def test_resolve_spy_operation_enemy_dominant_no_reveal_and_spy_lost(monkeypatch):
    # own_rand == enemy_rand, but enemy_spies=1000 >> spies=1, so the first
    # processed object gets multiplier >> 10 => that spy gets executed
    # immediately, which then stops any further objects being processed
    # (spies - executed_spies hits 0) - and "enemy won" means nothing gets
    # revealed for that object either.
    monkeypatch.setattr(services, "get_latest_spy_operation", lambda db, cId: None)
    monkeypatch.setattr(services, "has_active_embassy", lambda db, cId, eId: False)
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

    ok, code, msg, entry = services.resolve_spy_operation(QueuedCursor(), 1, 2, 1, "units")

    assert ok is True
    assert decrease_calls == [1]
    assert entry is not None
