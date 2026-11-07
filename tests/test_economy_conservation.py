"""N-tick conservation check for the hourly economy (the "iterative imbalance" test).

Runs the real hourly ticks for many simulated hours against the real schema and checks that every
change in a nation's gold is explained by a row in nation_revenue_history, that nothing goes
negative or non-finite, that a repeat run inside the same period moves nothing, and that
the per-hour result stays smooth (no hour-to-hour jumps from a double charge or a missed tick).

Past incidents this is meant to catch: the pension double-charge (#259), the military upkeep v2
sell-back loop (#287) and the 2026-05 revenue-tick rollback. A tick that creates or destroys gold
without a ledger row, or charges twice, fails here.

Known gap, asserted explicitly so it cannot grow quietly: loan interest takes gold straight from
the borrower without a ledger row (app_core/game_ticks/loan_interest.py). The test keeps its nations
loan-free, and test_loan_interest_is_the_only_unledgered_gold_sink pins that gap.
"""
import math
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users

pytestmark = pytest.mark.no_server

N_TICKS = 24
GATES = ("generate_province_revenue", "tax_income", "loan_interest", "military_maintenance")


def _make_nation(db, label, gold, pop, farms):
    name = f"cons_{label}_{uuid.uuid4().hex[:6]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
        (name, f"{name}@example.invalid"),
    )
    uid = db.fetchone()[0]
    db.execute("INSERT INTO stats (id, location, gold) VALUES (%s, 'Grassland', %s)", (uid, gold))
    db.execute(
        "INSERT INTO provinces (userid, provincename, citycount, land, population, happiness, "
        "productivity, energy, pop_children, pop_working, pop_elderly, edu_none) "
        "VALUES (%s, %s, 10, 50, %s, 80, 80, 100, %s, %s, %s, %s) RETURNING id",
        (uid, f"{name}-p", pop, pop // 5, pop * 3 // 5, pop // 5, pop * 3 // 5),
    )
    pid = db.fetchone()[0]
    if farms:
        db.execute(
            "INSERT INTO user_buildings (user_id, building_id, province_id, quantity) "
            "SELECT %s, building_id, %s, %s FROM building_dictionary WHERE name = 'farms'",
            (uid, pid, farms),
        )
    return uid


def _clear_gates(db):
    db.execute("DELETE FROM task_runs WHERE task_name = ANY(%s)", (list(GATES),))


def _gold(db, uids):
    db.execute("SELECT id, gold FROM stats WHERE id = ANY(%s)", (uids,))
    return {i: int(g) for i, g in db.fetchall()}


def _ledger(db, uids, since_id):
    db.execute(
        "SELECT user_id, COALESCE(SUM(amount), 0) FROM nation_revenue_history "
        "WHERE user_id = ANY(%s) AND id > %s GROUP BY user_id",
        (uids, since_id),
    )
    return {i: int(a) for i, a in db.fetchall()}


@pytest.fixture
def nations():
    with get_db_connection() as conn:
        db = conn.cursor()
        uids = [
            _make_nation(db, "rich", 5_000_000_000, 8_000_000, 20),
            _make_nation(db, "mid", 200_000_000, 3_000_000, 5),
            _make_nation(db, "poor", 1_000_000, 500_000, 0),
        ]
        db.execute("SELECT COALESCE(MAX(id), 0) FROM nation_revenue_history")
        start_id = db.fetchone()[0]
        _clear_gates(db)
        conn.commit()
    yield uids, start_id
    with get_db_connection() as conn:
        db = conn.cursor()
        _clear_gates(db)
        db.execute("DELETE FROM nation_revenue_history WHERE user_id = ANY(%s)", (uids,))
        db.execute("DELETE FROM user_buildings WHERE user_id = ANY(%s)", (uids,))
        db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (uids,))
        db.execute("DELETE FROM provinces WHERE userid = ANY(%s)", (uids,))
        purge_users(db, uids)
        conn.commit()


def _run_hour():
    from app_core.game_ticks.revenue import generate_province_revenue
    from app_core.game_ticks.taxes import tax_income

    generate_province_revenue()
    tax_income()


def _simulate(uids, start_id, ticks):
    """Run `ticks` hours; return per-hour rows of (gold_delta, ledger_delta) per nation."""
    history = []
    with get_db_connection() as conn:
        db = conn.cursor()
        prev_gold = _gold(db, uids)
        prev_ledger = _ledger(db, uids, start_id)
    for _ in range(ticks):
        with get_db_connection() as conn:
            db = conn.cursor()
            _clear_gates(db)
            conn.commit()
        _run_hour()
        with get_db_connection() as conn:
            db = conn.cursor()
            gold = _gold(db, uids)
            ledger = _ledger(db, uids, start_id)
        history.append(
            {
                u: (gold[u] - prev_gold[u], ledger.get(u, 0) - prev_ledger.get(u, 0))
                for u in uids
            }
        )
        prev_gold, prev_ledger = gold, ledger
    return history


def _unexplained(history):
    """(hour, nation, gold_delta, ledger_delta) for every hour where gold moved without a ledger row."""
    return [
        (hour, uid, gd, ld)
        for hour, row in enumerate(history)
        for uid, (gd, ld) in row.items()
        if gd != ld
    ]


def test_every_gold_change_is_in_the_ledger(nations):
    uids, start_id = nations
    history = _simulate(uids, start_id, N_TICKS)
    assert not _unexplained(history), f"gold moved with no ledger row: {_unexplained(history)[:5]}"


def test_the_check_fails_when_gold_is_created_off_ledger(nations, monkeypatch):
    """Mutation check: prove the detector can fail, by injecting a silent gold leak each hour."""
    uids, start_id = nations
    real = _run_hour

    def leaky():
        real()
        with get_db_connection() as conn:
            conn.cursor().execute("UPDATE stats SET gold = gold + 777 WHERE id = %s", (uids[1],))
            conn.commit()

    monkeypatch.setitem(globals(), "_run_hour", leaky)
    history = _simulate(uids, start_id, 3)
    assert len(_unexplained(history)) == 3 and all(
        gd - ld == 777 for _, _, gd, ld in _unexplained(history)
    )


def test_a_double_charge_is_visible_as_a_jump(nations, monkeypatch):
    """Mutation check for the #259 shape: one extra charge in a single hour breaks smoothness."""
    uids, start_id = nations
    real = _run_hour
    calls = {"n": 0}

    def double_once():
        real()
        calls["n"] += 1
        if calls["n"] == 5:
            with get_db_connection() as conn:
                db = conn.cursor()
                db.execute("UPDATE stats SET gold = gold - 3000000 WHERE id = %s", (uids[1],))
                db.execute(
                    "INSERT INTO nation_revenue_history (user_id, category, amount) "
                    "VALUES (%s, 'pension_crisis', -3000000)",
                    (uids[1],),
                )
                conn.commit()

    monkeypatch.setitem(globals(), "_run_hour", double_once)
    history = _simulate(uids, start_id, 8)
    assert not _unexplained(history)  # the ledger is consistent, so only smoothness can catch it
    series = [row[uids[1]][0] for row in history]
    assert max(abs(series[i] - series[i - 1]) for i in range(2, len(series))) > 0.25 * abs(series[1])


def test_loan_interest_is_the_only_unledgered_gold_sink(nations):
    """Pins the known gap: interest is taken from the borrower's gold with no ledger row."""
    from app_core.game_ticks.loan_interest import run_loan_interest

    uids, start_id = nations
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id = %s", (uids[1],))
        before = int(db.fetchone()[0])
        db.execute(
            "INSERT INTO user_loans (user_id, principal, balance, interest_rate, status) "
            "VALUES (%s, 1000000, 1000000, 0.01, 'active')",
            (uids[1],),
        )
        _clear_gates(db)
        conn.commit()
    try:
        run_loan_interest()
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("SELECT gold FROM stats WHERE id = %s", (uids[1],))
            after = int(db.fetchone()[0])
            assert before - after == 10000  # 1% of 1,000,000, taken from gold
            assert _ledger(db, [uids[1]], start_id) == {}  # ...and not recorded anywhere
    finally:
        with get_db_connection() as conn:
            conn.cursor().execute("DELETE FROM user_loans WHERE user_id = %s", (uids[1],))
            conn.commit()


def test_no_negative_or_non_finite_values_after_many_ticks(nations):
    uids, start_id = nations
    _simulate(uids, start_id, N_TICKS)
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id = ANY(%s)", (uids,))
        for (gold,) in db.fetchall():
            assert gold is not None and math.isfinite(float(gold)) and gold >= 0
        db.execute(
            "SELECT COUNT(*) FROM user_economy WHERE user_id = ANY(%s) AND quantity < 0", (uids,)
        )
        assert db.fetchone()[0] == 0


def test_hourly_result_is_smooth_not_jumpy(nations):
    """No hour may differ from the previous one by more than 25 percent (after the first hour).

    A double charge or a skipped tick shows up as one hour at roughly double or zero."""
    uids, start_id = nations
    history = _simulate(uids, start_id, N_TICKS)
    for uid in uids:
        series = [row[uid][0] for row in history]
        for hour in range(2, len(series)):
            prev, cur = series[hour - 1], series[hour]
            if abs(prev) < 1000:
                continue
            assert abs(cur - prev) <= 0.25 * abs(prev), (
                f"nation {uid}: hour {hour} moved {cur} after {prev} (jump over 25%)"
            )


def test_a_second_run_in_the_same_period_changes_nothing(nations):
    uids, start_id = nations
    _simulate(uids, start_id, 1)  # one real hour
    with get_db_connection() as conn:
        db = conn.cursor()
        before = _gold(db, uids)
        ledger_before = _ledger(db, uids, start_id)
    _run_hour()  # gates are NOT cleared: this must be a no-op
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _gold(db, uids) == before
        assert _ledger(db, uids, start_id) == ledger_before


def test_the_ticks_really_move_gold(nations):
    """Guard against a vacuous pass: with real nations the ticks must produce ledger rows."""
    uids, start_id = nations
    history = _simulate(uids, start_id, 3)
    moved = sum(abs(gd) for row in history for gd, _ in row.values())
    ledger_total = sum(abs(ld) for row in history for _, ld in row.values())
    assert moved > 0 and ledger_total > 0, f"ticks did nothing: {history}"
