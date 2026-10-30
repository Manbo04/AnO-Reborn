"""Vacation mode rules (#suggestions 1559986341339598890).

DB-free: rules are exercised against a scripted cursor with a fixed clock.
"""
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask, session

from app_core import vacation
from tests._fake_db import FakeCursor, cursor_ctx

pytestmark = pytest.mark.no_server

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _enable_cursor(mode=False, started=None, ended=None, at_war=False):
    return FakeCursor(
        [
            ("FOR UPDATE", [(mode, started, ended)]),
            ("FROM wars", [(1,)] if at_war else []),
        ]
    )


def _updated(cur):
    return any(s.startswith("UPDATE users SET vacation_mode") for s in cur.sql_log())


def test_cannot_enable_during_war():
    cur = _enable_cursor(at_war=True)
    ok, msg = vacation.enable_vacation(cur, 1, now=NOW)
    assert not ok and "war" in msg
    assert not _updated(cur)


def test_enable_without_war_sets_flag():
    cur = _enable_cursor()
    ok, _ = vacation.enable_vacation(cur, 1, now=NOW)
    assert ok and _updated(cur)


def test_cannot_disable_before_72_hours():
    started = NOW - timedelta(hours=71)
    cur = _enable_cursor(mode=True, started=started)
    ok, msg = vacation.disable_vacation(cur, 1, now=NOW)
    assert not ok and "1h" in msg
    assert not _updated(cur)


def test_can_disable_after_72_hours():
    started = NOW - timedelta(hours=72, minutes=1)
    cur = _enable_cursor(mode=True, started=started)
    ok, _ = vacation.disable_vacation(cur, 1, now=NOW)
    assert ok and _updated(cur)


def test_cooldown_blocks_reenable_for_7_days():
    ended = NOW - timedelta(days=6, hours=23)
    cur = _enable_cursor(ended=ended)
    ok, msg = vacation.enable_vacation(cur, 1, now=NOW)
    assert not ok and "cooldown" in msg
    assert not _updated(cur)


def test_reenable_allowed_after_cooldown():
    ended = NOW - timedelta(days=7, minutes=1)
    cur = _enable_cursor(ended=ended)
    ok, _ = vacation.enable_vacation(cur, 1, now=NOW)
    assert ok and _updated(cur)


def test_state_reports_when_changes_are_allowed():
    on = FakeCursor([("FROM users", [(True, NOW - timedelta(hours=10), None)])])
    st = vacation.get_vacation_state(on, 1, now=NOW)
    assert st["on"] and st["can_disable_at"] == NOW + timedelta(hours=62)
    off = FakeCursor([("FROM users", [(False, None, NOW - timedelta(days=1))])])
    st = vacation.get_vacation_state(off, 1, now=NOW)
    assert not st["on"] and st["can_enable_at"] == NOW + timedelta(days=6)


def test_missing_columns_mean_not_on_vacation():
    class Boom(FakeCursor):
        def execute(self, sql, params=None):
            if "vacation_" in str(sql):
                raise RuntimeError("column does not exist")
            super().execute(sql, params)

    assert vacation.is_on_vacation(Boom(), 1) is False
    ok, msg = vacation.enable_vacation(Boom(), 1, now=NOW)
    assert not ok and "isn't available" in msg
    assert vacation.get_vacation_state(Boom(), 1)["available"] is False


# ----------------------------------------------------------- declare_war


class _Econ:
    def __init__(self, user_id):
        self.id = user_id


def _declare(monkeypatch, vacationers):
    """Call the real declare_war with attacker 1 -> defender 2."""
    from wars import routes as wars_routes

    cur = FakeCursor()
    monkeypatch.setattr(wars_routes, "get_request_cursor", cursor_ctx(cur))
    monkeypatch.setattr(wars_routes, "Economy", _Econ)
    monkeypatch.setattr(
        wars_routes, "is_on_vacation", lambda db, uid, lock=False: uid in vacationers
    )
    monkeypatch.setattr(wars_routes, "error", lambda code, msg: (code, msg))
    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context(
        "/declare_war",
        method="POST",
        data={"defender": "2", "warType": "Raze", "description": "x"},
    ):
        session["user_id"] = 1
        result = wars_routes.declare_war.__wrapped__()
    return result, cur


def test_war_declaration_against_vacationer_is_blocked(monkeypatch):
    result, cur = _declare(monkeypatch, vacationers={2})
    assert result == (403, vacation.ON_VACATION_DEFENDER_MSG)
    assert not any("INSERT INTO wars" in s for s in cur.sql_log())


def test_vacationer_cannot_declare_war(monkeypatch):
    result, cur = _declare(monkeypatch, vacationers={1})
    assert result == (403, vacation.ON_VACATION_ATTACKER_MSG)
    assert not any("INSERT INTO wars" in s for s in cur.sql_log())


def test_no_vacation_decorator_blocks_hostile_actions(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    monkeypatch.setattr("database.get_request_cursor", cursor_ctx(FakeCursor()))
    monkeypatch.setattr(vacation, "is_on_vacation", lambda db, uid, lock=False: True)
    monkeypatch.setattr("helpers.error", lambda code, msg: (code, msg))

    @vacation.no_vacation
    def attack():
        return "attacked"

    with app.test_request_context("/x", method="POST"):
        session["user_id"] = 1
        assert attack() == (403, vacation.ON_VACATION_ATTACKER_MSG)
