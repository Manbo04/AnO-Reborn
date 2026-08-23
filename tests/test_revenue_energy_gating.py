"""countries.get_revenue() should gate projected net production/upkeep by
local energy and input-resource availability, not just gold -- mirroring
app_core/game_ticks/revenue.py's real hourly tick via the shared
app_core.economy.affordability.compute_affordable_units gate.

Before this fix, a building with plenty of gold but no local energy or no
input resource still showed its full projected output on /revenue -- which
is the exact "it says I have it but nothing happens" pattern reported
repeatedly for silos, aerodromes, reactors, and aluminium refineries.

Runs fully offline: a FakeCursor is passed directly as get_revenue()'s `db`
argument, so reuse_or_new_cursor() reuses it instead of opening a real pool
connection -- no live DB, no Flask server required.
"""

import pytest

pytestmark = pytest.mark.no_server


class FakeCursor:
    def __init__(self, fetchone_returns=None, fetchall_queue=None):
        self._fetchone_returns = list(fetchone_returns or [])
        self._fetchall_queue = list(fetchall_queue or [])

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        if self._fetchone_returns:
            return self._fetchone_returns.pop(0)
        return None

    def fetchall(self):
        if self._fetchall_queue:
            return self._fetchall_queue.pop(0)
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run_get_revenue(monkeypatch, coal_stock, bauxite_stock=10_000):
    import countries
    from database import query_cache

    monkeypatch.setattr(query_cache, "get", lambda key: None)
    monkeypatch.setattr(query_cache, "set", lambda key, val, ttl_seconds=None: None)
    # Coalition-tax lookup hits a real DB connection outside the passed-in
    # cursor (module-level cache miss on first call in-process) -- not what
    # this test is about, so make it a no-op like an unaffiliated nation.
    monkeypatch.setattr(countries, "get_coalition_members_table", lambda: None)

    db = FakeCursor(
        fetchone_returns=[
            (10_000_000,),  # gold -- never the constraint in this test
            (None,),  # policies
            (1000, 0, 0),  # demographic pop_working/children/elderly sums
        ],
        fetchall_queue=[
            [(100, 10, 50, 1000)],  # provinces: id, land, productivity, population
            [],  # unlocked tech/upgrades
            [
                (100, "coal_burners", 1),
                (100, "aluminium_refineries", 1),
            ],  # buildings for province 100 -- the exact building class
            # (energy consumer + a real input resource) from the recurring
            # "revenue page says fine, tick produces nothing" reports.
            [
                ("coal", coal_stock),
                ("bauxite", bauxite_stock),
                ("rations", 0),
                ("consumer_goods", 0),
            ],
            [],  # distribution-capacity buildings for CG tax multiplier
        ],
    )

    return countries.get_revenue(1, db=db)


def test_energy_shortfall_zeroes_out_downstream_consumer_net_production(monkeypatch):
    # coal_burners need 11 coal/unit; only 5 in stock -- the burner can't run
    # at all, so it produces 0 of its usual 4 energy/unit, and the
    # aluminium_refinery (1 energy/unit, plenty of bauxite) can't run either
    # even though its own input resource is fully stocked.
    rev = _run_get_revenue(monkeypatch, coal_stock=5)

    # Gross stays the unconstrained theoretical projection either way.
    assert rev["gross"]["energy"] == 4
    assert rev["gross"]["aluminium"] == 64

    assert rev["net"]["energy"] == 0
    assert rev["net"]["coal"] == 0  # upkeep not drawn from a building that didn't run
    assert rev["net"]["aluminium"] == 0  # blocked on energy, not bauxite
    assert rev["net"]["bauxite"] == 0  # refinery never ran, so never drew bauxite either


def test_sufficient_coal_lets_energy_flow_to_the_consumer_this_same_pass(monkeypatch):
    # Enough coal for the one coal_burner (11) to run and produce 4 energy,
    # which the aluminium_refinery (1 energy/unit) can then draw on in the
    # same projection pass, since power plants are processed before
    # consumers (variables.BUILDINGS order) -- and it has plenty of bauxite.
    rev = _run_get_revenue(monkeypatch, coal_stock=11)

    assert rev["net"]["coal"] == -11
    assert rev["net"]["aluminium"] == 64
    assert rev["net"]["bauxite"] == -256


def test_bauxite_shortfall_still_gates_independently_of_energy(monkeypatch):
    # Energy is fine (plenty of coal), but bauxite is short -- the refinery
    # should be gated by its input resource even with energy solved.
    rev = _run_get_revenue(monkeypatch, coal_stock=110, bauxite_stock=100)

    assert rev["net"]["aluminium"] == 0
    assert rev["net"]["bauxite"] == 0
