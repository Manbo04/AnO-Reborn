"""Tick and display share one formula module each (Phase 4).

These guard against the copies coming back: the revenue page and the
hourly tick must get the same numbers from the same function.
"""

import variables
from app_core.economy import tax_formula
from app_core.economy.military_upkeep import military_upkeep_rows


def test_tax_formula_food_penalty_and_grace():
    big = [(1_000_000, 30, 200_000, 600_000, 200_000)] * 2
    full = tax_formula.compute_tax_income(big, 0, [0.0, 0.0], False)["income"]
    starved = tax_formula.compute_tax_income(big, 0, [0.0, 0.0], False, effective_rations=0)["income"]
    assert starved == int(full * variables.NO_FOOD_TAX_MULTIPLIER) or abs(
        starved - full * variables.NO_FOOD_TAX_MULTIPLIER
    ) <= 1
    small = [(10_000, 10, 2_000, 6_000, 2_000)]
    a = tax_formula.compute_tax_income(small, 0, [0.0], False)["income"]
    b = tax_formula.compute_tax_income(small, 0, [0.0], False, effective_rations=0)["income"]
    assert a == b  # grace period: one small province pays no food penalty


def test_tax_formula_no_provinces():
    assert tax_formula.compute_tax_income([], 10, [], False)["income"] == 0


def test_display_and_tick_read_same_upkeep_rows():
    from database import get_db_cursor
    from psycopg2.extras import RealDictCursor

    with get_db_cursor(cursor_factory=RealDictCursor) as db:
        all_rows = military_upkeep_rows(db)
        for uid in {r["user_id"] for r in all_rows}:
            mine = military_upkeep_rows(db, uid)
            assert sorted((r["resource"], r["required_amount"]) for r in mine) == sorted(
                (r["resource"], r["required_amount"]) for r in all_rows if r["user_id"] == uid
            )


def test_iron_dome_gasoline_in_upkeep_rows():
    """The revenue page missed dome gasoline while the tick charged it."""
    from database import get_db_cursor
    from psycopg2.extras import RealDictCursor
    from app_core.military.iron_dome import DOME_UPKEEP_GASOLINE

    with get_db_cursor(cursor_factory=RealDictCursor) as db:
        db.execute("SELECT id FROM provinces WHERE userid = 16 ORDER BY id LIMIT 1")
        pid = db.fetchone()["id"]
        db.execute("SELECT COALESCE(SUM(quantity), 0) AS q FROM province_iron_domes WHERE province_id = %s", (pid,))
        before = int(db.fetchone()["q"])
        db.execute("DELETE FROM province_iron_domes WHERE province_id = %s", (pid,))
        db.execute("INSERT INTO province_iron_domes (province_id, quantity) VALUES (%s, 2)", (pid,))
        try:
            gas = {r["resource"]: r["required_amount"] for r in military_upkeep_rows(db, 16)}.get("gasoline", 0)
            db.execute("SELECT COALESCE(SUM(d.quantity), 0) AS q FROM province_iron_domes d JOIN provinces p ON p.id = d.province_id WHERE p.userid = 16")
            assert gas >= int(db.fetchone()["q"]) * DOME_UPKEEP_GASOLINE > 0
        finally:
            db.execute("DELETE FROM province_iron_domes WHERE province_id = %s", (pid,))
            if before:
                db.execute("INSERT INTO province_iron_domes (province_id, quantity) VALUES (%s, %s)", (pid, before))
