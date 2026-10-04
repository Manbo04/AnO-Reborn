"""Repeat-last-attack button + war-end/peace news (Silent, 2026-10-04)."""

import pytest
from flask import render_template, session

from tests.test_ui_war_and_icon_centering import app  # noqa: F401 (fixture)

import wars.routes as wr
from attack_scripts import war_orchestrator as wo

pytestmark = pytest.mark.no_server


PARTICIPANT_CTX = dict(
    attacker="10",
    attacker_name="Gondor",
    defender="20",
    defender_name="Mordor",
    cId_type="attacker",
    war_id=77,
    war_type="Raze",
    agressor_message="",
    attacker_info={"morale": 90, "supplies": 1500},
    defender_info={"morale": 35, "supplies": 400},
    peace_to_send=20,
    spyCount=12,
)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.connection = self

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def commit(self):
        pass


@pytest.mark.parametrize("template", ["war_v2.html", "war.html"])
def test_war_page_shows_repeat_button_only_with_a_last_attack(app, template):
    with app.test_request_context("/war/77"):
        without = render_template(template, repeat_attack=None, **PARTICIPANT_CTX)
        with_btn = render_template(
            template,
            repeat_attack={"war_id": 77, "label": "500 soldiers, 20 tanks, 10 artillery"},
            **PARTICIPANT_CTX,
        )
    assert "/war/77/repeat_attack" not in without
    assert 'action="/war/77/repeat_attack"' in with_btn
    assert "500 soldiers, 20 tanks, 10 artillery" in with_btn


def test_war_result_has_attack_again_button(app):
    with app.test_request_context("/warResult"):
        html = render_template(
            "warResult.html",
            winner="Gondor",
            win_condition="annihilation",
            defender_result={"nation_name": "Mordor"},
            attacker_result={"nation_name": "Gondor"},
            repeat_attack={"war_id": 77, "label": "5 icbms at their tanks"},
        )
    assert 'action="/war/77/repeat_attack"' in html
    assert "Attack again" in html
    assert "5 icbms at their tanks" in html
    assert 'href="/war/77"' in html


def test_last_attack_is_stored_per_war_and_capped(app):
    with app.test_request_context("/"):
        for war_id in range(1, wr._LAST_ATTACK_MAX_WARS + 3):
            wr._remember_last_attack(war_id, {"domain": "ground", "units": {"soldiers": war_id}})
        store = session["last_attack"]
        assert len(store) == wr._LAST_ATTACK_MAX_WARS
        assert "1" not in store and "2" not in store
        assert wr._last_attack_for(12)["units"] == {"soldiers": 12}
        assert wr._last_attack_for(999) is None
        assert wr._last_attack_for(None) is None


def test_last_attack_label():
    assert (
        wr._last_attack_label({"units": {"soldiers": 1500, "tanks": 0, "artillery": 3}})
        == "1,500 soldiers, 3 artillery"
    )
    assert (
        wr._last_attack_label({"special": True, "units": {"icbms": 2}, "target": "cruisers"})
        == "2 icbms at their cruisers"
    )


def _call_repeat(app, monkeypatch, entry, war_row, owned, special=None):
    calls = {}

    class FakeUnits:
        def __init__(self, user_id, war_id=None):
            self.user_id, self.war_id = user_id, war_id

        def attach_units(self, units, count):
            calls["attach"] = (dict(units), count)

    monkeypatch.setattr(wr, "Units", FakeUnits)
    monkeypatch.setattr(wr.Military, "get_military", staticmethod(lambda cid: dict(owned)))
    monkeypatch.setattr(wr.Military, "get_special", staticmethod(lambda cid: dict(special or {})))
    monkeypatch.setattr(wr, "get_request_cursor", lambda: _Ctx(FakeCursor([war_row] if war_row else [])))
    monkeypatch.setattr(
        wr,
        "_resolve_special_attack",
        lambda au, eId, target: calls.setdefault("special", (eId, target)) and "special-fired",
    )
    monkeypatch.setattr(wr, "error", lambda code, msg: (code, msg))
    view = wr.repeat_attack
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    with app.test_request_context("/war/77/repeat_attack", method="POST"):
        session["user_id"] = 10
        if entry:
            session["last_attack"] = {"77": entry}
        resp = view(77)
        return resp, calls, dict(session)


class _Ctx:
    def __init__(self, cur):
        self.cur = cur

    def __enter__(self):
        return self.cur

    def __exit__(self, *a):
        return False


def test_repeat_caps_amounts_at_what_is_still_owned(app, monkeypatch):
    entry = {"domain": "ground", "units": {"soldiers": 1000, "tanks": 50, "artillery": 20}}
    resp, calls, sess = _call_repeat(
        app, monkeypatch, entry, (10, 20), {"soldiers": 600, "tanks": 50, "artillery": 0}
    )
    assert calls["attach"] == ({"soldiers": 600, "tanks": 50, "artillery": 0}, 3)
    assert resp.status_code == 302 and resp.location.endswith("/warResult")
    assert sess["enemy_id"] == 20 and sess["war_domain"] == "ground"


def test_repeat_special_attack_reuses_target(app, monkeypatch):
    entry = {"special": True, "units": {"icbms": 3}, "target": "tanks"}
    resp, calls, sess = _call_repeat(
        app, monkeypatch, entry, (20, 10), {}, special={"icbms": 5}
    )
    assert calls["attach"] == ({"icbms": 3}, 1)
    assert calls["special"] == (20, "tanks")
    assert sess["enemy_id"] == 20


@pytest.mark.parametrize(
    "entry,war_row,owned,msg",
    [
        (None, (10, 20), {}, "No previous attack"),
        ({"domain": "ground", "units": {"soldiers": 5, "tanks": 1, "artillery": 1}}, None, {}, "war is over"),
        ({"domain": "ground", "units": {"soldiers": 5, "tanks": 1, "artillery": 1}}, (30, 40), {}, "war is over"),
        ({"domain": "ground", "units": {"soldiers": 5, "tanks": 1, "artillery": 1}}, (10, 20), {}, "none of those units"),
    ],
)
def test_repeat_rejects_bad_states(app, monkeypatch, entry, war_row, owned, msg):
    resp, calls, _ = _call_repeat(app, monkeypatch, entry, war_row, owned)
    assert resp[0] == 400 and msg in resp[1]
    assert "attach" not in calls


def test_war_end_news_goes_to_both_sides_with_spoils():
    cur = FakeCursor([(1, "Gondor"), (2, "Mordor")])
    wo._record_war_end_news(cur, 1, 2, {"iron": 1200, "oil": 30})
    sql, params = cur.executed[-1]
    assert "INSERT INTO news" in sql
    assert params[0] == 1 and "You won the war" in params[1] and "1,200 iron, 30 oil" in params[1]
    assert params[2] == 2 and "lost the war against Gondor" in params[3] and "1,200 iron" in params[3]


def test_war_end_news_with_nothing_looted():
    cur = FakeCursor([(1, "Gondor"), (2, "Mordor")])
    wo._record_war_end_news(cur, 1, 2, {})
    params = cur.executed[-1][1]
    assert "nothing left to loot" in params[1]
    assert "found nothing to loot" in params[3]


def test_peace_news_lists_paid_terms():
    cur = FakeCursor([(1, "Gondor"), (2, "Mordor")])
    wr._record_peace_news(cur, 1, 2, {"money": "5000", "iron": "10"})
    params = cur.executed[-1][1]
    assert params[0] == 2 and "Gondor accepted your peace offer" in params[1]
    assert "You received: 5,000 money, 10 iron." in params[1]
    assert params[2] == 1 and "You paid: 5,000 money, 10 iron." in params[3]
