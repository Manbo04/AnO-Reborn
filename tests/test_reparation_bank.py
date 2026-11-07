"""Reparations on a loser's coalition-bank balance (flag reparation_taxes_bank)."""
import time
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users
from tests._prod_guard import refuse_production

refuse_production()
pytestmark = pytest.mark.no_server


def _flag(on):
    with get_db_connection() as conn:
        conn.cursor().execute(
            "INSERT INTO feature_flags (key, enabled, rollout_percent, description) "
            "VALUES ('reparation_taxes_bank', %s, 100, 't') "
            "ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled",
            (on,),
        )
        conn.commit()
    from app_core import feature_flags

    feature_flags._flags(force=True)


def _lumber(db, uid):
    db.execute(
        "SELECT COALESCE(SUM(ue.quantity), 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = 'lumber'",
        (uid,),
    )
    return int(db.fetchone()[0])


@pytest.fixture
def world():
    made = {"users": [], "wars": [], "cols": []}

    def _user(db, lumber=0):
        name = f"repb_{uuid.uuid4().hex[:6]}"
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) "
            "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
            (name, f"{name}@example.invalid"),
        )
        uid = db.fetchone()[0]
        db.execute("INSERT INTO stats (id, location) VALUES (%s, 'Grassland')", (uid,))
        db.execute(
            "INSERT INTO user_economy (user_id, resource_id, quantity) "
            "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name = 'lumber'",
            (uid, lumber),
        )
        made["users"].append(uid)
        return uid

    def _make(war_type="Sustained", a_morale=100, d_morale=0, status=None,
              deposited=1000, withdrawn=0, bank_lumber=5000, stock=1000):
        with get_db_connection() as conn:
            db = conn.cursor()
            winner, loser, other = _user(db), _user(db, stock), _user(db)
            col = 900000000 + uuid.uuid4().int % 90000000
            db.execute(
                "INSERT INTO colnames (id, type, name, date) VALUES (%s, 'Open', %s, '2026-10-06')",
                (col, f"repb{col}"),
            )
            db.execute("INSERT INTO colbanks (colid, lumber) VALUES (%s, %s)", (col, bank_lumber))
            db.execute(
                "INSERT INTO col_bank_contributions (coalition_id, user_id, resource, total_deposited, total_withdrawn) "
                "VALUES (%s, %s, 'lumber', %s, %s), (%s, %s, 'lumber', %s, 0)",
                (col, loser, deposited, withdrawn, col, other, bank_lumber - (deposited - withdrawn)),
            )
            now = time.time()
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, last_visited, "
                "peace_date, attacker_morale, defender_morale, status) "
                "VALUES (%s, %s, %s, 'test', %s, %s, %s, %s, %s, COALESCE(%s, 'active')) RETURNING id",
                (winner, loser, war_type, now, now, now, a_morale, d_morale, status),
            )
            made["wars"].append(db.fetchone()[0])
            made["cols"].append(col)
            conn.commit()
        return winner, loser, other, col

    yield _make
    _flag(False)
    with get_db_connection() as conn:
        db = conn.cursor()
        for w in made["wars"]:
            db.execute("DELETE FROM wars WHERE id = %s", (w,))
        for c in made["cols"]:
            db.execute("DELETE FROM col_bank_transactions WHERE coalition_id = %s", (c,))
            db.execute("DELETE FROM col_bank_contributions WHERE coalition_id = %s", (c,))
            db.execute("DELETE FROM colbanks WHERE colid = %s", (c,))
            db.execute("DELETE FROM colnames WHERE id = %s", (c,))
        db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (made["users"],))
        purge_users(db, made["users"])
        conn.commit()


def _bank(col):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT lumber FROM colbanks WHERE colid = %s", (col,))
        bank = int(db.fetchone()[0])
        db.execute("SELECT user_id, total_deposited, total_withdrawn FROM col_bank_contributions WHERE coalition_id = %s", (col,))
        return bank, {u: (int(d), int(w or 0)) for u, d, w in db.fetchall()}


@pytest.mark.parametrize("flag_on", [False, True])
def test_stockpile_tax_is_identical_with_flag_on_or_off(world, flag_on):
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(flag_on)
    winner, loser, _o, _c = world()
    war_reparation_tax()
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _lumber(db, loser) == 800
        # winner gets 200 from the stockpile, plus 200 from the bank only when the flag is on
        assert _lumber(db, winner) == (400 if flag_on else 200)


def test_flag_off_leaves_the_bank_untouched(world):
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(False)
    _w, loser, other, col = world()
    war_reparation_tax()
    bank, contrib = _bank(col)
    assert bank == 5000 and contrib[loser] == (1000, 0)


@pytest.mark.parametrize("war_type, rate", [("Sustained", 0.2), ("Raze", 0.05)])
def test_flag_on_taxes_personal_balance_only(world, war_type, rate):
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(True)
    winner, loser, other, col = world(war_type)
    war_reparation_tax()
    bank, contrib = _bank(col)
    took = int(1000 * rate)
    assert bank == 5000 - took
    assert contrib[loser] == (1000, took)  # personal balance shrinks via total_withdrawn
    assert contrib[other] == (4000, 0)  # other members' share untouched


def test_withdrawn_balance_is_not_taxed_twice_and_negative_is_ignored(world):
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(True)
    _w, loser, _o, col = world(deposited=1000, withdrawn=900, bank_lumber=5000)
    war_reparation_tax()
    bank, contrib = _bank(col)
    assert bank == 5000 - 20 and contrib[loser][1] == 920  # 20% of the 100 left


def test_clamped_to_what_the_bank_holds(world):
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(True)
    winner, loser, _o, col = world(deposited=1000, bank_lumber=50)
    war_reparation_tax()
    bank, contrib = _bank(col)
    assert bank == 0 and contrib[loser][1] == 50  # took only the 50 the bank had


@pytest.mark.parametrize("kwargs", [
    {"a_morale": 100, "d_morale": 100},
    {"a_morale": 60, "d_morale": 40, "status": "ended"},
])
def test_no_bank_tax_without_morale_break(world, kwargs):
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(True)
    _w, loser, _o, col = world(**kwargs)
    war_reparation_tax()
    bank, contrib = _bank(col)
    assert bank == 5000 and contrib[loser] == (1000, 0)


def test_daily_gate_means_the_bank_is_taxed_once(world):
    from app_core.game_ticks.common import run_once_per_period
    from app_core.game_ticks.taxes import war_reparation_tax

    _flag(True)
    _w, loser, _o, col = world()
    with get_db_connection() as conn:
        conn.cursor().execute("DELETE FROM task_runs WHERE task_name = 'war_reparation_tax'")
        conn.commit()
    try:
        assert run_once_per_period("war_reparation_tax", 9031, war_reparation_tax) is True
        assert run_once_per_period("war_reparation_tax", 9031, war_reparation_tax) is False
        assert _bank(col)[0] == 5000 - 200
    finally:
        with get_db_connection() as conn:
            conn.cursor().execute("DELETE FROM task_runs WHERE task_name = 'war_reparation_tax'")
            conn.commit()
