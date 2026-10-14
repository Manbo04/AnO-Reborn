import datetime

from app_core.game_ticks import population2 as p2

AFTER = p2.POP2_START + datetime.timedelta(days=p2.GRACE_DAYS + 1)
DURING = p2.POP2_START + datetime.timedelta(days=1)


def test_homes_formula_and_transit_cap():
    assert p2.homes(0, 0, {}) == 2_000_000
    assert p2.homes(10, 100, {}) == 2_000_000 + 500_000 + 3_000_000
    assert p2.homes(0, 0, {"railways": 5}) == int(2_000_000 * 1.05)
    assert p2.homes(0, 0, {"monorails": 50}) == int(2_000_000 * 1.30)


def test_housing_factor_linear_to_zero_at_120():
    assert p2.housing_factor(900, 1000) == 1.0
    assert abs(p2.housing_factor(1100, 1000) - 0.5) < 1e-9
    assert p2.housing_factor(1200, 1000) == 0.0
    assert p2.housing_factor(5000, 1000) == 0.0


def test_no_education_penalty_on_births():
    # same inputs regardless of schooling: births only depend on housing,
    # happiness and food
    a = p2.births(1_000_000, 2_000_000, 4_000_000, 50, 1.0, dt=1)
    assert a == int(1_000_000 * 0.025 * 1.0 * 1.0 * 1.0)


def test_hospitals_cover_one_million_people_each_at_any_population():
    unc, _ = p2.death_rates(0, 10_000_000, 0, False)
    cov, _ = p2.death_rates(100, 10_000_000, 0, False)
    assert unc == 0.06 and abs(cov - 0.02) < 1e-9
    assert p2.hospital_cover(667, 666_000_000) == 1.0
    assert abs(p2.hospital_cover(8, 666_000_000) - 8_000_000 / 666_000_000) < 1e-12
    healthy, _ = p2.death_rates(0, 1_000_000, 0, True)
    assert abs(healthy - 0.06 * 0.7) < 1e-9


def test_settlers_halved_vs_announcement_and_capped():
    s = p2.settlers(0, 2_000_000, 50, 1.0, dt=1)
    assert s == int(min(0.10 * 2_000_000, 500_000) * 1.0)
    big = p2.settlers(0, 10_000_000_000, 100, 1.0, dt=1)
    assert big == int(500_000 * 1.5)
    assert p2.settlers(5_000_000, 2_000_000, 100, 1.0) == 0
    assert p2.settlers(0, 2_000_000, 100, 0.0) == 0


def test_emigration_only_after_grace_and_only_above_120():
    assert p2.emigrants(1_100_000, 1_000_000) == 0
    assert p2.emigrants(1_500_000, 1_000_000, dt=1) == int(300_000 * 0.02)
    prov = {"id": 1, "population": 1_500_000, "pop_children": 300_000,
            "pop_working": 1_000_000, "pop_elderly": 200_000,
            "citycount": 0, "land": 0, "happiness": 50, "pollution": 0}
    # homes = 2M base -> 75% full; use a tiny-homes province instead
    big = dict(prov, population=5_000_000, pop_children=1_000_000,
               pop_working=3_500_000, pop_elderly=500_000)
    during = p2.simulate_nation([big], {}, 1.0, False, True, now=DURING)[1]
    after = p2.simulate_nation([big], {}, 1.0, False, True, now=AFTER)[1]
    assert sum(after) < sum(during)  # emigration abroad only after the 14 days


def test_migration_moves_overflow_to_free_homes_conserving_people():
    out = p2.distribute_migration(
        [{"id": 1, "pop": 3_000_000, "homes": 2_000_000},
         {"id": 2, "pop": 500_000, "homes": 2_000_000}], dt=1)
    assert out[1] == -50_000 and out[2] <= 50_000 and out[2] >= 49_999
    assert p2.distribute_migration(
        [{"id": 1, "pop": 3_000_000, "homes": 2_000_000}], dt=1) == {1: 0}


def test_week_sim_empty_nation_grows_and_full_nation_does_not_explode():
    small = {"id": 1, "population": 100_000, "pop_children": 30_000,
             "pop_working": 60_000, "pop_elderly": 10_000,
             "citycount": 1, "land": 10, "happiness": 60, "pollution": 10}
    s = dict(small)
    for _ in range(24 * 7):
        c, w, e = p2.simulate_nation([s], {}, 1.0, False, False, now=DURING)[1]
        s.update(pop_children=c, pop_working=w, pop_elderly=e, population=c + w + e)
    assert s["population"] > 100_000 * 1.5  # settlers fill empty homes
    assert s["population"] < 3_000_000  # but not instantly


def _starving_nation(now):
    prov = {
        "id": 1, "population": 10_000_000, "pop_children": 2_000_000,
        "pop_working": 7_000_000, "pop_elderly": 1_000_000,
        "citycount": 0, "land": 1_000, "happiness": 50, "pollution": 0,
    }
    out = p2.simulate_nation([prov], {}, 0.0, False, False, now=now)
    return sum(out[1])


def test_no_starvation_deaths_during_grace_week():
    now = p2.STARVATION_GRACE_END - datetime.timedelta(minutes=1)
    assert p2.starvation_grace_active(now)
    # food_ratio 0: births stop but nobody starves (only normal deaths, < 0.1%)
    assert _starving_nation(now) > 10_000_000 * 0.999


def test_starvation_after_grace_is_quarter_percent_per_tick():
    now = p2.STARVATION_GRACE_END + datetime.timedelta(minutes=1)
    assert not p2.starvation_grace_active(now)
    left = _starving_nation(now)
    assert 10_000_000 * 0.99 < left < 10_000_000 * 0.9985
class _RecCursor:
    def __init__(self):
        self.params = None

    def execute(self, sql, params=None):
        self.params = params

    def fetchall(self):
        return []


def test_healthcare_lookup_casts_str_ids_to_int():
    # the nation page passes the id as a str; text[] = integer broke the
    # growth rate ("Growth rate showing 0") for every viewer
    cur = _RecCursor()
    p2.fetch_healthcare_users(cur, ["69697871"])
    assert cur.params == ([69697871],)
