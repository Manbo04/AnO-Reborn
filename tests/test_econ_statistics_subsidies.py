"""Industrial Subsidies must cut upkeep in the expenses breakdown too."""
from contextlib import contextmanager
from unittest.mock import MagicMock

import countries
import variables


def _run(policies):
    building = variables.POLICY_SUBSIDIES_AFFECTED_BUILDINGS[0]
    state = {"last": ""}
    cur = MagicMock()

    def execute(sql, params=None):
        state["last"] = sql

    def fetchall():
        if "user_buildings" in state["last"]:
            return [{"name": building, "total_quantity": 10}]
        return []

    def fetchone():
        if "policies" in state["last"]:
            return {"education": policies}
        return None

    cur.execute.side_effect = execute
    cur.fetchall.side_effect = fetchall
    cur.fetchone.side_effect = fetchone

    @contextmanager
    def fake(db, cursor_factory=None):
        yield cur

    orig = countries.reuse_or_new_cursor
    countries.reuse_or_new_cursor = fake
    try:
        return building, countries.get_econ_statistics(987654 + len(policies), db=cur)
    finally:
        countries.reuse_or_new_cursor = orig


def test_subsidies_reduce_money_expenses():
    b, base = _run([])
    _, sub = _run([variables.POLICY_INDUSTRIAL_SUBSIDIES])
    unit_type = next(
        t for t, bs in variables.INFRA_TYPE_BUILDINGS.items() if b in bs
    )
    full = int(variables.INFRA[f"{b}_money"]) * 10
    assert base[unit_type]["money"] == full
    assert sub[unit_type]["money"] == int(
        full * variables.POLICY_SUBSIDIES_UPKEEP_REDUCTION
    )
