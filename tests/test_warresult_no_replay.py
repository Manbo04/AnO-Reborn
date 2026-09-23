"""Regression test for a real replay/double-resolution race found live
2026-09-23 while auditing wars/routes.py during the account
cross-contamination investigation (unrelated to that bug, found along the
way).

/warResult resolves an attack using attack_units/enemy_id/war_domain read
from the client-side signed session cookie (this app has no server-side
session store). session.pop()'ing that data at the end of a successful
request does NOT stop a second, concurrent request carrying the SAME
still-valid stale cookie (double-click, browser back+resubmit, two tabs)
from also reading the identical attack_units and re-entering the fight
branch -- Military.fight() -> persist_fight_results() applies casualties
AND, on a war-ending morale drop, transfers resources from loser to
winner, via its OWN independent connection with no lock and no per-attack
idempotency token.

wars.last_visited looked reusable for a one-shot debounce gate, but it's
a `real` (single-precision float) column -- too coarse to represent a
current Unix timestamp precisely enough for a sub-second comparison,
confirmed empirically while writing this test (an intended 1-second
window behaved unpredictably due to rounding, not an actual locking
problem -- both racers passed, or both failed, seemingly at random).
Fixed with migrations/0081, a dedicated wars.last_attack_resolved_at
DOUBLE PRECISION column: a WHERE-guarded UPDATE only succeeds once inside
a 1-second window for a given war, checked and consumed BEFORE any combat
resolution runs.

This test patches Military.fight() and resolve_defender_composition() to
fixed, cheap results -- neither is part of this bug or its fix, and
standing them up with a fully realistic combat setup (buildings, tech,
upgrades) would only add fragility to a test that's really about the
session-replay race, not combat balance. It still calls the real,
unmodified warResult() view function directly and checks the guard's
actual observable effect: wars.attacker_supplies, which the real
(unpatched) Units.save() decrements once per successful resolution.

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
ATTACKER_SUPPLIES = 200
SUPPLY_COST = 50


def _create_user(db, suffix):
    username = f"warresult_{suffix}_{uuid.uuid4().hex[:8]}"
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
        # last_attack_resolved_at is left NULL (its default) -- the guard's
        # own "IS NULL" branch is the natural starting state for a freshly
        # created war, no staleness workaround needed.
        db.execute(
            """
            INSERT INTO wars
                (attacker, defender, war_type, agressor_message,
                 start_date, last_visited, attacker_supplies, defender_supplies)
            VALUES (%s, %s, 'Sustained', 'test war', %s, %s, %s, 200)
            RETURNING id
            """,
            (attacker_id, defender_id, now, now, ATTACKER_SUPPLIES),
        )
        war_id = db.fetchone()[0]
        conn.commit()

    yield {"attacker_id": attacker_id, "defender_id": defender_id, "war_id": war_id}

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM wars WHERE id = %s", (war_id,))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (attacker_id, defender_id))
        conn.commit()


def test_two_concurrent_warresult_calls_resolve_only_once(war_pair):
    from app import app
    from attack_scripts.Nations import Military
    import attack_scripts.war_orchestrator as war_orchestrator
    from wars.routes import warResult

    attacker_id = war_pair["attacker_id"]
    defender_id = war_pair["defender_id"]
    war_id = war_pair["war_id"]

    attack_units_dict = {
        "user_id": attacker_id,
        "selected_units": {"soldiers": 1, "tanks": 0, "artillery": 0},
        "bonuses": None,
        "supply_costs": SUPPLY_COST,
        "available_supplies": ATTACKER_SUPPLIES,
        "war_id": war_id,
        "selected_units_list": ["soldiers", "tanks", "artillery"],
    }

    def _fake_fight(attacker, defender):
        return attacker.user_id, "skirmish", [0]

    def _fake_resolve_defender_composition(defender_id_arg, domain):
        return (
            ["soldiers", "tanks", "artillery"],
            {"soldiers": 0, "tanks": 0, "artillery": 0},
        )

    barrier = threading.Barrier(2)
    errors = []

    def _run(slot):
        try:
            with app.test_request_context("/warResult", method="GET"):
                from flask import session

                session["user_id"] = attacker_id
                session["enemy_id"] = defender_id
                session["war_domain"] = "ground"
                session["attack_units"] = dict(attack_units_dict)
                barrier.wait(timeout=5)
                warResult()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    with patch.object(Military, "fight", staticmethod(_fake_fight)), patch.object(
        war_orchestrator, "resolve_defender_composition", _fake_resolve_defender_composition
    ):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert not errors, f"racer thread(s) raised: {errors}"

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT attacker_supplies FROM wars WHERE id = %s", (war_id,))
        remaining_supplies = db.fetchone()[0]

    assert remaining_supplies == ATTACKER_SUPPLIES - SUPPLY_COST, (
        f"attacker_supplies is {remaining_supplies}, expected exactly "
        f"{ATTACKER_SUPPLIES - SUPPLY_COST} (one resolution's worth deducted) -- "
        f"a lower value means the same stale attack_units session data "
        f"resolved the fight twice"
    )
