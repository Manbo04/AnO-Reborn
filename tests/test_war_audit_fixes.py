"""Regression tests for the war audit (2026-10-13): peace offers, special
units, attack replay, surrender, spy sabotage gating, alliance treaties, bot
refill, treaty notices and the retired /defense page.

Real local database + the real Flask app/test client (same style as
tests/test_declare_war_no_duplicate_race.py).
"""
import time
import uuid
from pathlib import Path

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users

ROOT = Path(__file__).resolve().parent.parent


def _mk_user(db, tag, gold=0):
    name = f"waraudit_{tag}_{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, '2026-10-13', 'x', 'normal') RETURNING id",
        (name, f"{name}@example.com"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', %s) "
        "ON CONFLICT (id) DO UPDATE SET gold = EXCLUDED.gold",
        (uid, gold),
    )
    return uid


def _mk_war(db, a, d):
    now = time.time()
    db.execute(
        "INSERT INTO wars (attacker, defender, war_type, agressor_message, "
        "start_date, last_visited) VALUES (%s, %s, 'Sustained', 'x', %s, %s) "
        "RETURNING id",
        (a, d, now, now),
    )
    return db.fetchone()[0]


@pytest.fixture
def world():
    """Four nations: A/B at war, C/D at war (with a pending peace offer)."""
    ids = {}
    with get_db_connection() as conn:
        db = conn.cursor()
        ids["a"] = _mk_user(db, "a", gold=1_000_000)
        ids["b"] = _mk_user(db, "b", gold=1_000_000)
        ids["c"] = _mk_user(db, "c")
        ids["d"] = _mk_user(db, "d")
        ids["war_ab"] = _mk_war(db, ids["a"], ids["b"])
        ids["war_cd"] = _mk_war(db, ids["c"], ids["d"])
        db.execute(
            "INSERT INTO peace (author, demanded_resources, demanded_amount) "
            "VALUES (%s, 'money', '5') RETURNING id",
            (ids["c"],),
        )
        ids["peace_cd"] = db.fetchone()[0]
        db.execute(
            "UPDATE wars SET peace_offer_id=%s WHERE id=%s",
            (ids["peace_cd"], ids["war_cd"]),
        )
        conn.commit()
    yield ids
    with get_db_connection() as conn:
        db = conn.cursor()
        users = [ids[k] for k in ("a", "b", "c", "d")]
        db.execute(
            "DELETE FROM wars WHERE attacker = ANY(%s) OR defender = ANY(%s)",
            (users, users),
        )
        db.execute("DELETE FROM peace WHERE author = ANY(%s)", (users,))
        db.execute(
            "DELETE FROM nation_treaties WHERE sender_id = ANY(%s) "
            "OR recipient_id = ANY(%s)",
            (users, users),
        )
        db.execute("DELETE FROM news WHERE destination_id = ANY(%s)", (users,))
        purge_users(db, users)
        conn.commit()


def _client_as(uid, **session_extra):
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = uid
        for k, v in session_extra.items():
            s[k] = v
    return client


def _q(sql, params=()):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(sql, params)
        try:
            return db.fetchall()
        except Exception:
            return []


# ---------------------------------------------------------------------------
# peace offers
# ---------------------------------------------------------------------------


def test_peace_offer_only_touches_its_own_war_and_notifies(world):
    client = _client_as(world["a"])
    resp = client.post(
        f"/send_peace_offer/{world['war_ab']}/{world['b']}", data={"money": "100"}
    )
    assert resp.status_code in (302, 303)
    # The unrelated C/D offer is untouched (the old UPDATE had no WHERE).
    row = _q(
        "SELECT author, demanded_resources, demanded_amount FROM peace WHERE id=%s",
        (world["peace_cd"],),
    )[0]
    assert tuple(row) == (world["c"], "money", "5")
    # A/B got their own offer
    (offer_id,) = _q("SELECT peace_offer_id FROM wars WHERE id=%s", (world["war_ab"],))[0]
    assert offer_id and offer_id != world["peace_cd"]
    # Re-offering edits only that offer
    client.post(
        f"/send_peace_offer/{world['war_ab']}/{world['b']}", data={"money": "7"}
    )
    assert _q("SELECT demanded_amount FROM peace WHERE id=%s", (offer_id,))[0][0] == "7"
    assert _q("SELECT demanded_amount FROM peace WHERE id=%s", (world["peace_cd"],))[0][0] == "5"
    # In-game notice reached the receiver
    news = _q("SELECT message FROM news WHERE destination_id=%s", (world["b"],))
    assert any("PEACE OFFER" in r[0] for r in news)


def test_peace_offer_rejects_negative_and_foreign_and_ended_wars(world):
    client = _client_as(world["a"])
    assert (
        client.post(
            f"/send_peace_offer/{world['war_ab']}/{world['b']}", data={"money": "-50"}
        ).status_code
        == 400
    )
    # not a participant of C/D
    assert (
        client.post(
            f"/send_peace_offer/{world['war_cd']}/{world['d']}", data={"money": "1"}
        ).status_code
        == 403
    )
    _q("UPDATE wars SET peace_date=%s WHERE id=%s", (time.time(), world["war_ab"]))
    assert (
        client.post(
            f"/send_peace_offer/{world['war_ab']}/{world['b']}", data={"money": "1"}
        ).status_code
        == 400
    )


def test_accepting_peace_is_all_or_nothing(world):
    # A demands money (B can pay) AND an absurd amount of oil (B cannot).
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO peace (author, demanded_resources, demanded_amount) "
            "VALUES (%s, 'money,oil', '1000,99999999999') RETURNING id",
            (world["a"],),
        )
        pid = db.fetchone()[0]
        db.execute("UPDATE wars SET peace_offer_id=%s WHERE id=%s", (pid, world["war_ab"]))
        conn.commit()
    client = _client_as(world["b"])
    resp = client.post("/peace_offers", data={"peace_offer": str(pid), "decision": "1"})
    assert resp.status_code == 400
    assert _q("SELECT gold FROM stats WHERE id=%s", (world["b"],))[0][0] == 1_000_000
    assert _q("SELECT gold FROM stats WHERE id=%s", (world["a"],))[0][0] == 1_000_000
    assert _q("SELECT peace_date FROM wars WHERE id=%s", (world["war_ab"],))[0][0] is None


def test_accepting_peace_pays_and_ends_the_war(world):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO peace (author, demanded_resources, demanded_amount) "
            "VALUES (%s, 'money', '1000') RETURNING id",
            (world["a"],),
        )
        pid = db.fetchone()[0]
        db.execute("UPDATE wars SET peace_offer_id=%s WHERE id=%s", (pid, world["war_ab"]))
        conn.commit()
    client = _client_as(world["b"])
    resp = client.post("/peace_offers", data={"peace_offer": str(pid), "decision": "1"})
    assert resp.status_code in (302, 303)
    assert _q("SELECT gold FROM stats WHERE id=%s", (world["b"],))[0][0] == 999_000
    assert _q("SELECT gold FROM stats WHERE id=%s", (world["a"],))[0][0] == 1_001_000
    assert _q("SELECT peace_date FROM wars WHERE id=%s", (world["war_ab"],))[0][0] is not None
    # the other war's offer was not swept up
    assert _q("SELECT peace_date FROM wars WHERE id=%s", (world["war_cd"],))[0][0] is None


def test_negative_demand_in_a_stored_offer_cannot_steal(world):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO peace (author, demanded_resources, demanded_amount) "
            "VALUES (%s, 'money', '-500') RETURNING id",
            (world["a"],),
        )
        pid = db.fetchone()[0]
        db.execute("UPDATE wars SET peace_offer_id=%s WHERE id=%s", (pid, world["war_ab"]))
        conn.commit()
    resp = _client_as(world["b"]).post(
        "/peace_offers", data={"peace_offer": str(pid), "decision": "1"}
    )
    assert resp.status_code == 400
    assert _q("SELECT gold FROM stats WHERE id=%s", (world["b"],))[0][0] == 1_000_000


# ---------------------------------------------------------------------------
# special units / attack replay / AP
# ---------------------------------------------------------------------------


def test_warchoose_rejects_unknown_special_unit_and_foreign_war(world):
    client = _client_as(world["a"], enemy_id=world["b"])
    assert (
        client.post(
            f"/warchoose/{world['war_ab']}", data={"special_unit": "anything_goes"}
        ).status_code
        == 400
    )
    # a war A is not part of
    assert (
        client.post(
            f"/warchoose/{world['war_cd']}", data={"special_unit": "icbms"}
        ).status_code
        == 400
    )
    # ended war
    _q("UPDATE wars SET peace_date=%s WHERE id=%s", (time.time(), world["war_ab"]))
    assert (
        client.post(
            f"/warchoose/{world['war_ab']}", data={"special_unit": "icbms"}
        ).status_code
        == 400
    )


def test_attack_slot_resolves_once_per_prepared_attack(world):
    from app import app
    from wars.routes import _claim_attack_slot

    wid = world["war_ab"]
    with app.test_request_context("/"):
        from flask import session

        with get_db_connection() as conn:
            db = conn.cursor()
            session["attack_issued_at"] = time.time()
            assert _claim_attack_slot(db, wid) is True
            # same prepared attack replayed (saved cookie, double click, 2 tabs)
            assert _claim_attack_slot(db, wid) is False
            time.sleep(0.02)
            # a freshly prepared attack is fine again
            session["attack_issued_at"] = time.time()
            assert _claim_attack_slot(db, wid) is True
            # cookie issued before that resolution is dead
            session["attack_issued_at"] = time.time() - 60
            assert _claim_attack_slot(db, wid) is False
            conn.commit()


def test_attack_slot_refuses_ended_war(world):
    from app import app
    from wars.routes import _claim_attack_slot

    _q("UPDATE wars SET peace_date=%s WHERE id=%s", (time.time(), world["war_ab"]))
    with app.test_request_context("/"):
        from flask import session

        session["attack_issued_at"] = time.time()
        with get_db_connection() as conn:
            assert _claim_attack_slot(conn.cursor(), world["war_ab"]) is False


def test_empty_attacker_never_wins_even_against_an_empty_domain():
    from attack_scripts.combat_helpers import resolve_battle_outcome, zero_out_empty_side

    # both sides empty: defender holds
    a, d = zero_out_empty_side(3.0, 2.0, 0, 0)
    assert a == 0
    assert resolve_battle_outcome(a, d, 0, 0)[0] is True
    # real attacker vs empty defender still wins
    a, d = zero_out_empty_side(3.0, 2.0, 5, 0)
    assert d == 0 and resolve_battle_outcome(a, d, 5, 0)[0] is False
    # empty attacker vs real defender loses
    a, d = zero_out_empty_side(3.0, 2.0, 0, 5)
    assert resolve_battle_outcome(a, d, 0, 5)[0] is True


# ---------------------------------------------------------------------------
# surrender
# ---------------------------------------------------------------------------


def test_surrender_ends_war_for_the_other_side_once(world):
    client = _client_as(world["b"])
    assert client.post(f"/war/{world['war_ab']}/surrender", data={}).status_code == 400
    assert (
        _client_as(world["c"])
        .post(f"/war/{world['war_ab']}/surrender", data={"confirm": "yes"})
        .status_code
        == 403
    )
    resp = client.post(f"/war/{world['war_ab']}/surrender", data={"confirm": "yes"})
    assert resp.status_code in (302, 303)
    assert _q("SELECT peace_date FROM wars WHERE id=%s", (world["war_ab"],))[0][0] is not None
    assert any(
        "surrendered" in r[0]
        for r in _q("SELECT message FROM news WHERE destination_id=%s", (world["a"],))
    )
    assert any(
        "You surrendered" in r[0]
        for r in _q("SELECT message FROM news WHERE destination_id=%s", (world["b"],))
    )
    # second submit: already over
    assert (
        client.post(f"/war/{world['war_ab']}/surrender", data={"confirm": "yes"}).status_code
        == 400
    )


def test_war_pages_offer_surrender_and_no_dead_defense_button():
    for name in ("war.html", "war_v2.html"):
        text = (ROOT / "templates" / name).read_text()
        assert "/surrender" in text
    for name in ("wars.html", "wars_v2.html"):
        assert "/defense" not in (ROOT / "templates" / name).read_text()


def test_defense_url_redirects_to_wars(world):
    resp = _client_as(world["a"]).get("/defense")
    assert resp.status_code in (301, 302)
    assert resp.headers["Location"].endswith("/wars")


# ---------------------------------------------------------------------------
# spies
# ---------------------------------------------------------------------------


def test_sabotage_needs_a_war_but_recon_does_not(world):
    from app_core.intelligence.services import check_spy_target

    with get_db_connection() as conn:
        db = conn.cursor()
        a, b, c = world["a"], world["b"], world["c"]
        assert check_spy_target(db, a, b, "sabotage")[0] is True  # at war
        for op in ("sabotage", "sabotage_strategic", "assassinate_spies"):
            ok, code, _msg, _t = check_spy_target(db, a, c, op)  # no war
            assert (ok, code) == (False, 403)
        assert check_spy_target(db, a, c, "units")[0] is True
        assert check_spy_target(db, a, a, "units")[0] is False
        assert check_spy_target(db, a, 999999999, "units")[:2] == (False, 404)
        assert check_spy_target(db, a, "abc", "units")[:2] == (False, 400)


# ---------------------------------------------------------------------------
# alliance treaties, join_ally, treaty notices
# ---------------------------------------------------------------------------


def _treaty(db, a, b, kind):
    db.execute(
        "INSERT INTO nation_treaties (sender_id, recipient_id, treaty_type, status) "
        "VALUES (%s, %s, %s, 'active') RETURNING id",
        (a, b, kind),
    )
    return db.fetchone()[0]


def test_alliance_lets_a_partner_join_once_only(world):
    # C is allied with B (defender of war A->B); C may join against A, once.
    with get_db_connection() as conn:
        db = conn.cursor()
        _treaty(db, world["c"], world["b"], "alliance")
        conn.commit()
    client = _client_as(world["c"])
    first = client.post(f"/wars/{world['war_ab']}/join_ally")
    assert first.status_code in (302, 303)
    second = client.post(f"/wars/{world['war_ab']}/join_ally")
    assert second.status_code == 400
    rows = _q(
        "SELECT count(*) FROM wars WHERE attacker=%s AND defender=%s AND peace_date IS NULL",
        (world["c"], world["a"]),
    )
    assert rows[0][0] == 1


def test_alliance_blocks_declaring_war_like_a_nap(world):
    from app import app

    with get_db_connection() as conn:
        db = conn.cursor()
        _treaty(db, world["a"], world["c"], "alliance")
        conn.commit()
    text = (ROOT / "wars" / "routes.py").read_text()
    assert "treaty_type IN ('non_aggression', 'alliance')" in text
    assert "treaty_type IN ('mutual_defense', 'alliance')" in text
    assert app  # app imports fine with the change


def test_cancelling_a_treaty_notifies_the_other_side(world):
    with get_db_connection() as conn:
        db = conn.cursor()
        tid = _treaty(db, world["a"], world["b"], "embassy")
        conn.commit()
    resp = _client_as(world["a"]).post(f"/treaties/cancel/{tid}")
    assert resp.status_code in (302, 303)
    assert _q("SELECT status FROM nation_treaties WHERE id=%s", (tid,))[0][0] == "cancelled"
    assert any(
        "cancelled" in r[0]
        for r in _q("SELECT message FROM news WHERE destination_id=%s", (world["b"],))
    )


# ---------------------------------------------------------------------------
# bots + nuke text
# ---------------------------------------------------------------------------


def test_bots_in_or_near_war_flags_active_and_recent_only(world):
    from app_core.bots.service import _bots_in_or_near_war, LOOT_RECOVERY_SECONDS

    now = time.time()
    with get_db_connection() as conn:
        db = conn.cursor()
        old = _mk_war(db, world["c"], world["a"])
        db.execute(
            "UPDATE wars SET peace_date=%s WHERE id=%s",
            (now - LOOT_RECOVERY_SECONDS - 3600, old),
        )
        recent = _mk_war(db, world["d"], world["a"])
        db.execute(
            "UPDATE wars SET peace_date=%s WHERE id=%s", (now - 3600, recent)
        )
        got = _bots_in_or_near_war(db, [world["a"], world["b"], world["c"], world["d"]], now)
        conn.commit()
    # a: in active war A/B; b: active; c: active C/D; d: active D/C + recent
    assert {world["a"], world["b"], world["c"], world["d"]} <= got
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("UPDATE wars SET peace_date=%s WHERE id=%s", (now - 10 * 86400, world["war_ab"]))
        db.execute("UPDATE wars SET peace_date=%s WHERE id=%s", (now - 10 * 86400, world["war_cd"]))
        db.execute("UPDATE wars SET peace_date=%s WHERE id=%s", (now - 10 * 86400, recent))
        got = _bots_in_or_near_war(db, [world["a"], world["b"], world["c"], world["d"]], now)
        conn.commit()
    assert got == set()


def test_nuke_copy_no_longer_claims_it_cannot_be_intercepted():
    for rel in ("templates/nuclear_strike.html", "templates/mechanics/war.html"):
        assert "can't be intercepted" not in (ROOT / rel).read_text()
