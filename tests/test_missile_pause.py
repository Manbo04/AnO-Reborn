"""Temporary pause on missile launches (flag pause_missile_launches).

While the flag is ON, nuclear strikes, ICBM strikes and cruise missile strikes must be
refused BEFORE anything is spent. While OFF, behaviour is unchanged.
"""

import pytest

from app_core import missile_pause

pytestmark = pytest.mark.no_server

# Real seeded account (same one the other route tests use) so app.py's before_request
# lookup finds a user and lets the request reach the route.
REAL_SESSION_USER_ID = 16


# ---------------------------------------------------------------- flag helper
def test_paused_follows_the_flag(monkeypatch):
    monkeypatch.setattr(
        missile_pause, "is_on", lambda key, user_id=None, default=False: True
    )
    assert missile_pause.paused(1) is True
    monkeypatch.setattr(
        missile_pause, "is_on", lambda key, user_id=None, default=False: False
    )
    assert missile_pause.paused(1) is False


def test_paused_uses_the_right_flag_key(monkeypatch):
    seen = {}

    def fake(key, user_id=None, default=False):
        seen["key"] = key
        return False

    monkeypatch.setattr(missile_pause, "is_on", fake)
    missile_pause.paused(5)
    assert seen["key"] == "pause_missile_launches"


def test_paused_fails_open_if_the_flag_cannot_be_read(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(missile_pause, "is_on", boom)
    # a flag read problem must never freeze the game
    assert missile_pause.paused(1) is False


# ------------------------------------------------------------- nukes (plan_strike)
class _FakeDb:
    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return [(1, "Attacker"), (2, "Defender")]

    def fetchone(self):
        return (0,)


def _patch_plan_strike_inputs(monkeypatch, nukes=3, influence=5_000_000):
    from wars import nuclear

    monkeypatch.setattr(nuclear, "_active_war", lambda db, war_id, attacker_id: 2)
    monkeypatch.setattr(nuclear, "fresh_influence", lambda db, uid: influence)
    monkeypatch.setattr(nuclear, "is_retaliation", lambda *a, **k: False)
    monkeypatch.setattr(nuclear, "_nuke_count", lambda db, uid: nukes)
    monkeypatch.setattr(nuclear, "volleys_used", lambda *a, **k: 0)
    monkeypatch.setattr(
        nuclear,
        "enemy_provinces",
        lambda db, enemy_id: [
            {"id": 10, "population": 1000, "land": 10, "citycount": 2}
        ],
    )
    return nuclear


def test_plan_strike_is_blocked_while_paused(monkeypatch):
    nuclear = _patch_plan_strike_inputs(monkeypatch)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    plan = nuclear.plan_strike(_FakeDb(), 1, 99, province_id=10)
    assert plan["blocked"] == missile_pause.MESSAGE


def test_plan_strike_is_blocked_for_the_salvo_path_too(monkeypatch):
    nuclear = _patch_plan_strike_inputs(monkeypatch)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    plan = nuclear.plan_strike(_FakeDb(), 1, 99, salvo=True)
    assert plan["blocked"] == missile_pause.MESSAGE


def test_plan_strike_is_unchanged_when_not_paused(monkeypatch):
    nuclear = _patch_plan_strike_inputs(monkeypatch)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    plan = nuclear.plan_strike(_FakeDb(), 1, 99, province_id=10)
    assert plan["blocked"] is None


def test_execute_strike_refuses_while_paused(monkeypatch):
    nuclear = _patch_plan_strike_inputs(monkeypatch)
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    with pytest.raises(nuclear.StrikeError) as exc:
        nuclear.execute_strike(_FakeDb(), 1, 99, 10)
    assert missile_pause.MESSAGE in str(exc.value)


# ------------------------------------------------------------ cruise missiles
class _Boom:
    """Used as the DB cursor factory: any DB use means the route did not stop early."""

    def __call__(self, *a, **k):
        raise AssertionError("route touched the database while paused")


@pytest.mark.no_server
def test_cruise_missile_strike_is_refused_while_paused(client, monkeypatch):
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    monkeypatch.setattr("wars.routes._valid_strike_target", lambda t: True)
    monkeypatch.setattr("wars.routes.get_request_cursor", _Boom())
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID
    resp = client.post(
        "/cruise_missile_strike",
        data={"target_id": "1", "strike_target": "x", "missiles_count": "2"},
    )
    assert resp.status_code == 403
    assert b"paused" in resp.data


@pytest.mark.no_server
def test_cruise_missile_strike_still_reaches_the_normal_checks_when_not_paused(
    client, monkeypatch
):
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    monkeypatch.setattr("wars.routes._valid_strike_target", lambda t: True)
    reached = {"db": False}

    def fake_cursor(*a, **k):
        reached["db"] = True
        raise RuntimeError("stop here: past the pause check")

    monkeypatch.setattr("wars.routes.get_request_cursor", fake_cursor)
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID
    try:
        client.post(
            "/cruise_missile_strike",
            data={"target_id": "1", "strike_target": "x", "missiles_count": "2"},
        )
    except Exception:
        pass
    assert reached["db"] is True


# ---------------------------------------------------------------------- ICBMs
@pytest.mark.no_server
def test_icbm_strike_is_refused_while_paused_before_anything_else(client, monkeypatch):
    from wars import routes

    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    # attack_units=None would raise if the function got past the pause check
    with client.application.test_request_context("/wartarget", method="POST"):
        from flask import session

        session["user_id"] = REAL_SESSION_USER_ID
        result = routes._resolve_special_attack(None, 1, "tanks")
    body, code = result
    assert code == 403
    assert "paused" in str(body)


@pytest.mark.no_server
def test_icbm_strike_is_not_blocked_by_the_pause_check_when_off(client, monkeypatch):
    from wars import routes

    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    with client.application.test_request_context("/wartarget", method="POST"):
        from flask import session

        session["user_id"] = REAL_SESSION_USER_ID
        with pytest.raises(AttributeError):
            # past the pause check the function uses attack_units (None here)
            routes._resolve_special_attack(None, 1, "tanks")


# ---------------------------------------------------------- strategic airstrike
@pytest.mark.no_server
def test_strategic_airstrike_is_refused_while_paused(client, monkeypatch):
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    monkeypatch.setattr("wars.routes.get_request_cursor", _Boom())
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID
    resp = client.post(
        "/strategic_airstrike",
        data={"target_id": "1", "strike_target": "silo", "bombers_count": "50"},
    )
    assert resp.status_code == 403
    assert b"paused" in resp.data


@pytest.mark.no_server
def test_strategic_airstrike_still_reaches_the_normal_checks_when_not_paused(
    client, monkeypatch
):
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: False)
    reached = {"db": False}

    def fake_cursor(*a, **k):
        reached["db"] = True
        raise RuntimeError("stop here: past the pause check")

    monkeypatch.setattr("wars.routes.get_request_cursor", fake_cursor)
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID
    try:
        client.post(
            "/strategic_airstrike",
            data={"target_id": "1", "strike_target": "silo", "bombers_count": "50"},
        )
    except Exception:
        pass
    assert reached["db"] is True


# --------------------------------------------- drones are deliberately NOT paused
@pytest.mark.no_server
def test_drone_strike_is_not_affected_by_the_pause(client, monkeypatch):
    monkeypatch.setattr(missile_pause, "paused", lambda user_id=None: True)
    monkeypatch.setattr("wars.routes._valid_strike_target", lambda t: True)
    reached = {"db": False}

    def fake_cursor(*a, **k):
        reached["db"] = True
        raise RuntimeError("stop here: the drone route went on to its normal checks")

    monkeypatch.setattr("wars.routes.get_request_cursor", fake_cursor)
    with client.session_transaction() as sess:
        sess["user_id"] = REAL_SESSION_USER_ID
    try:
        client.post(
            "/drone_strike",
            data={"target_id": "1", "strike_target": "farms", "drones_count": "10"},
        )
    except Exception:
        pass
    # still reaches the database: drones are not paused
    assert reached["db"] is True


def test_message_names_every_paused_weapon():
    text = missile_pause.MESSAGE.lower()
    for word in ("nuclear", "icbm", "cruise", "airstrike"):
        assert word in text
