"""Regression test for a real replay/double-resolution race found live
2026-09-23 while auditing wars/routes.py during the account
cross-contamination investigation (unrelated to that bug, found along the
way).

/wartarget's POST branch (the legacy "special unit" attack path -- spies,
nukes/ICBMs sent as a lone special_unit selection through
warChoose->warAmount->wartarget, distinct from the dedicated
/nuclear_strike route also fixed this session) has the exact same replay
vulnerability as /warResult (see tests/test_warresult_no_replay.py's
docstring for the full mechanism): attack_units comes from the
client-side signed session cookie, and Military.special_fight() applies
casualties/infra damage and decrements the attacker's special unit via
its own independent, immediately-committing connection, with no
idempotency check. A double-click or resubmitted POST carrying the same
still-valid stale cookie could apply a second round of damage from a
single special attack.

Fixed by reusing the same wars.last_attack_resolved_at gate
(migrations/0081) added for warResult -- one shared "has this war's most
recent attack already been resolved" check covers both paths a war's
combat can be resolved through.

This test patches Military.special_fight() to a cheap fixed result and
counts calls -- the actual combat/casualty math inside special_fight()
isn't part of this bug or its fix, and standing up a fully realistic
setup would only add fragility to a test that's really about the
session-replay race. It still calls the real, unmodified warTarget() view
function directly.

Uses real concurrency (two threads, each with its own real Flask request
context sharing the same session state, a barrier forcing overlap)
against the real local ano_staging database -- same style as this
session's other wars/coalitions race fixes.
"""
import threading
import time
import uuid
from unittest.mock import patch

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


def _create_user(db, suffix):
    username = f"wartarget_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        """
        INSERT INTO users (username, email, date, hash, auth_type)
        VALUES (%s, %s, '2026-09-23', %s, 'normal')
        RETURNING id
        """,
        (username, f"{username}@example.com", TEST_PASSWORD),
    )
    return db.fetchone()[0]


@pytest.fixture
def war_pair():
    with get_db_connection() as conn:
        db = conn.cursor()
        attacker_id = _create_user(db, "attacker")
        defender_id = _create_user(db, "defender")
        now = time.time()
        db.execute(
            """
            INSERT INTO wars
                (attacker, defender, war_type, agressor_message, start_date, last_visited)
            VALUES (%s, %s, 'Sustained', 'test war', %s, %s)
            RETURNING id
            """,
            (attacker_id, defender_id, now, now),
        )
        war_id = db.fetchone()[0]
        conn.commit()

    yield {"attacker_id": attacker_id, "defender_id": defender_id, "war_id": war_id}

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM wars WHERE id = %s", (war_id,))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (attacker_id, defender_id))
        conn.commit()


def test_two_concurrent_wartarget_posts_resolve_only_once(war_pair):
    from app import app
    from attack_scripts.Nations import Military
    from wars.routes import warTarget

    attacker_id = war_pair["attacker_id"]
    defender_id = war_pair["defender_id"]
    war_id = war_pair["war_id"]

    attack_units_dict = {
        "user_id": attacker_id,
        "selected_units": {"nukes": 0},
        "bonuses": None,
        "supply_costs": 0,
        "available_supplies": 200,
        "war_id": war_id,
        "selected_units_list": ["nukes"],
    }

    call_count = {"n": 0}

    def _fake_special_fight(attacker, defender, target):
        call_count["n"] += 1
        return ({target: 0}, 0)

    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context(
                "/wartarget",
                method="POST",
                data={"targeted_unit": "soldiers"},
            ):
                from flask import session

                session["user_id"] = attacker_id
                session["enemy_id"] = defender_id
                session["attack_units"] = dict(attack_units_dict)
                barrier.wait(timeout=5)
                warTarget()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    with patch.object(Military, "special_fight", staticmethod(_fake_special_fight)):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert not errors, f"racer thread(s) raised: {errors}"

    assert call_count["n"] == 1, (
        f"Military.special_fight() was called {call_count['n']} times for a "
        f"single stale attack_units session snapshot raced twice, expected "
        f"exactly 1 -- this is the replay/double-resolution bug"
    )
