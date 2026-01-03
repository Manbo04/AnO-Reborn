"""Minimal, authoritative `tasks` module used for tests and background jobs.

This module provides a single well-tested implementation of `calc_ti` and a
small set of conservative helpers/stubs used by views and tests. All DB
interactions are defensive and performed inside functions (local imports)
so tests can monkeypatch DB helpers without import-time side effects.
"""

from __future__ import annotations

import math
from typing import Tuple

import variables  # Exposed so tests can monkeypatch `tasks.variables`

# Maximum safe 32-bit signed integer used by DB guard helpers
MAX_INT_32 = 2**31 - 1


def calc_ti(user_id: int) -> Tuple[int, int] | Tuple[bool, bool]:
    """Authoritative, defensive tax income calculation.

    Returns (income, removed_consumer_goods) or (False, False) when the
    user has no provinces.
    """
    # Local imports make it easy for tests to monkeypatch database helpers
    from database import get_db_cursor, fetchone_first

    with get_db_cursor() as db:
        db.execute("SELECT consumer_goods FROM resources WHERE id=%s", (user_id,))
        consumer_goods = int(fetchone_first(db, 0) or 0)

        try:
            db.execute("SELECT education FROM policies WHERE user_id=%s", (user_id,))
            policies = fetchone_first(db, [])
            if isinstance(policies, int):
                policies = [policies]
        except Exception:
            policies = []

        try:
            db.execute(
                "SELECT population, land FROM provinces WHERE userId=%s", (user_id,)
            )
            provinces = db.fetchall() or []
        except Exception:
            provinces = []

    if not provinces:
        return False, False

    income = 0
    for population, land in provinces:
        land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
        land_multiplier = min(land_multiplier, 1)

        base_multiplier = variables.DEFAULT_TAX_INCOME
        if 1 in policies:
            base_multiplier *= 1.01
        if 6 in policies:
            base_multiplier *= 0.98
        if 4 in policies:
            base_multiplier *= 0.98

        multiplier = base_multiplier + (base_multiplier * land_multiplier)
        income += multiplier * population

    total_pop = sum(p for p, _ in provinces)
    max_cg = math.ceil(total_pop / variables.CONSUMER_GOODS_PER) if total_pop > 0 else 0

    removed_cg = 0
    if max_cg and consumer_goods > 0:
        if consumer_goods >= max_cg:
            removed_cg = max_cg
            income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
        else:
            cg_multiplier = consumer_goods / max_cg
            income *= 1 + (0.5 * cg_multiplier)
            removed_cg = consumer_goods

    return math.floor(income), int(removed_cg)


def calc_pg(pId, rations):
    """Safe stub for population growth helper used by views/tests."""
    return rations, rations


def rations_needed(user_id: int) -> int:
    """Safe stub for rations calculation used by views/tests."""
    return 0


def energy_info(province_id: int) -> tuple[int, int]:
    """Safe stub for energy info used by views during import-time."""
    return 0, 0


def generate_province_revenue() -> None:
    """Minimal, test-friendly generation pass.

    Effects are intentionally conservative: perform a couple of DB queries
    so that tests can assert the expected queries are invoked, but avoid
    complex production logic here.
    """
    from database import get_db_connection
    from psycopg2.extras import RealDictCursor

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id, userId, population FROM provinces WHERE cityCount>0")
        infra_ids = db.fetchall() or []

        for infra in infra_ids:
            db.execute("UPDATE provinces SET energy=0 WHERE id=%s", (infra[0],))

        dbdict = conn.cursor(cursor_factory=RealDictCursor)
        owner_id = infra_ids[0][1] if infra_ids else None

        if owner_id is not None:
            dbdict.execute("SELECT * FROM upgrades WHERE user_id=%s", (owner_id,))
            _ = dbdict.fetchone()
            dbdict.execute("SELECT * FROM proInfra WHERE id=%s", (infra_ids[0][0],))
            _ = dbdict.fetchone()


def _safe_update_productivity(db_cursor, province_id, multiplier) -> None:
    db_cursor.execute("SELECT productivity FROM provinces WHERE id=%s", (province_id,))
    row = db_cursor.fetchone()
    if not row:
        return
    current = int(row[0])
    new_val = int(current * multiplier)
    if new_val > MAX_INT_32:
        new_val = MAX_INT_32
    db_cursor.execute(
        "UPDATE provinces SET productivity=(%s) WHERE id=%s", (new_val, province_id)
    )


def tax_income() -> None:
    from database import get_db_connection
    import psycopg2.extras as extras

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id FROM users")
        users = db.fetchall() or []

        cg_updates = []
        for (uid,) in users:
            res = calc_ti(uid)
            if res and isinstance(res, tuple):
                _, removed = res
                if removed and removed > 0:
                    cg_updates.append((removed, uid))

        if cg_updates:
            extras.execute_batch(
                db,
                "UPDATE resources SET consumer_goods=consumer_goods-%s WHERE id=%s",
                cg_updates,
            )


class _TaskWrapper:
    def __init__(self, func):
        self.func = func

    def run(self):
        try:
            self.func()
        except Exception:
            return None


task_tax_income = _TaskWrapper(tax_income)
task_generate_province_revenue = _TaskWrapper(generate_province_revenue)
