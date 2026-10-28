"""Weekly-vote balance + QoL: school capacities, workforce panel, building info."""
import pytest

import variables

pytestmark = pytest.mark.no_server


def test_school_capacities_are_multiples_of_5000_and_hs_needs_two_primaries():
    from app_core.game_ticks.population import calc_education_graduation

    for cap in (
        variables.PRIMARY_SCHOOL_CAPACITY,
        variables.HIGH_SCHOOL_CAPACITY,
        variables.UNIVERSITY_CAPACITY,
    ):
        assert cap % 5000 == 0
    assert variables.HIGH_SCHOOL_CAPACITY >= 2 * variables.PRIMARY_SCHOOL_CAPACITY
    stats = calc_education_graduation(10**9, [], 1, 1, 1, now=None, base_rate=1.0)
    assert stats["true_primary_capacity"] == variables.PRIMARY_SCHOOL_CAPACITY
    assert stats["hs_capacity"] == variables.HIGH_SCHOOL_CAPACITY
    # chain: one primary school caps what one high school can take in
    assert stats["passed_hs"] <= stats["passed_primary"]


def test_education_buildings_got_cheaper():
    prices = variables.PROVINCE_UNIT_PRICES
    assert prices["primary_school_price"] <= 2_000_000
    assert prices["high_school_resource"]["steel"] <= 30_000


def test_workforce_by_education_splits_jobs_and_workers():
    from app_core.economy.workforce import workforce_by_education

    matrices = {"farms": {"worker_count": 100, "education": {"edu_none": 1.0}},
                "universities": {"worker_count": 100, "education": {"edu_highschool": 0.8, "edu_college": 0.2}}}
    out = workforce_by_education(
        {"farms": 2, "universities": 1, "unknown": 5},
        {"edu_none": 50, "edu_highschool": 10, "edu_college": 0},
        100,
        matrices,
    )
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["edu_none"]["needed"] == 200
    assert rows["edu_highschool"]["needed"] == 80
    assert rows["edu_college"]["needed"] == 20
    # 100 working, 60 recorded -> 40 unrecorded count as no-schooling workers
    assert rows["edu_none"]["have"] == 90
    assert out["jobs_total"] == 300 and out["workers_total"] == 100
    assert out["unfilled_jobs"] == 200 and out["idle_workers"] == 0


def test_workforce_by_education_empty_is_safe():
    from app_core.economy.workforce import workforce_by_education

    out = workforce_by_education({}, {}, 0, {})
    assert out["jobs_total"] == 0 and out["unfilled_jobs"] == 0


def test_building_info_text_has_employment_and_upkeep():
    from app_core.economy.building_costs import building_info_text, enrich_building_row

    text = building_info_text("farms")
    assert "Employs 50,000 workers" in text and "base upkeep" in text
    assert building_info_text("farms", employs_only=True) == "Employs 50,000 workers (No schooling)"
    assert building_info_text("not_a_building") == ""
    assert enrich_building_row({"name": "farms", "display_name": "Farms"})["info"] == text


class _SellCursor:
    """Scripted cursor for province._mass_sell_buildings."""

    def __init__(self, war=False, owned=None):
        self.war = war
        self.owned = owned if owned is not None else {1: 5, 2: 0, 3: 2}
        self.executed = []
        self._last = []
        self.rowcount = 1
        self._pid = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        s = " ".join(sql.split())
        if "FROM wars" in s:
            self._last = [(1,)] if self.war else []
        elif "FROM provinces" in s:
            self._last = [(pid, f"P{pid}") for pid in sorted(self.owned)]
        elif "SELECT ub.quantity" in s:
            self._pid = params[1]
            self._last = [(self.owned[self._pid],)]
        elif s.startswith("UPDATE user_buildings"):
            num, _, pid = params[0], params[1], params[2]
            self.owned[pid] -= num
            self.rowcount = 1
        elif "SELECT gold" in s:
            self._last = [(1000,)]
        elif "education FROM policies" in s:
            self._last = [([],)]
        else:
            self._last = []

    def fetchone(self):
        return self._last[0] if self._last else None

    def fetchall(self):
        return list(self._last)


@pytest.fixture
def sell_env(monkeypatch):
    import province
    from app_core.economy import ledger

    credited = {"gold": 0, "res": {}}
    monkeypatch.setattr(province, "get_date", lambda: "2026-10-27")
    monkeypatch.setattr(ledger, "credit_gold", lambda db, uid, amt: credited.__setitem__("gold", credited["gold"] + amt))
    monkeypatch.setattr(
        ledger, "credit_resources",
        lambda db, uid, r: [credited["res"].__setitem__(k, credited["res"].get(k, 0) + v) for k, v in r.items()],
    )
    monkeypatch.setattr("app_core.economy.building_purchase._load_policies", lambda db, uid: [])
    return province, credited


def test_mass_sell_all_refunds_like_single_sell(sell_env):
    province, credited = sell_env
    db = _SellCursor()
    sold_in, units, gold, failures = province._mass_sell_buildings(db, 7, "primary_school", "all", 0, [1, 2, 3])
    price = variables.PROVINCE_UNIT_PRICES["primary_school_price"]
    assert (sold_in, units, failures) == (2, 7, [])  # province 2 had none
    assert gold == credited["gold"] == int(7 * price)
    assert credited["res"]["steel"] == 7 * variables.PROVINCE_UNIT_PRICES["primary_school_resource"]["steel"]
    assert db.owned == {1: 0, 2: 0, 3: 0}


def test_mass_sell_remove_never_goes_below_zero(sell_env):
    province, _ = sell_env
    db = _SellCursor()
    sold_in, units, _, _ = province._mass_sell_buildings(db, 7, "primary_school", "remove", 3, [1, 2, 3])
    assert units == 3 + 2  # capped by what each province has
    assert db.owned == {1: 2, 2: 0, 3: 0}


def test_mass_sell_blocked_during_war(sell_env):
    province, credited = sell_env
    db = _SellCursor(war=True)
    sold_in, units, gold, failures = province._mass_sell_buildings(db, 7, "primary_school", "all", 0, [1])
    assert (sold_in, units, gold) == (0, 0, 0) and failures
    assert credited["gold"] == 0 and db.owned[1] == 5


def test_calc_quote_matches_real_prices(monkeypatch):
    import province
    from app_core.economy.building_costs import get_build_cost, land_city_purchase_cost

    monkeypatch.setattr("app_core.economy.building_purchase._load_policies", lambda db, uid: [])
    monkeypatch.setattr(province, "active_keys", lambda db, uid: set())
    monkeypatch.setattr(province, "land_price_multiplier_for", lambda keys: 1.0)

    q = province._calc_quote(None, 1, "farms", 0, 10)
    c = get_build_cost("farms", [])
    assert q["gold"] == c["gold"] * 10 and q["units"] == 10
    assert q["resources"] == {r: a * 10 for r, a in c["resources"].items()}

    q = province._calc_quote(None, 1, "cityCount", 3, 8)
    assert q["gold"] == land_city_purchase_cost("cityCount", 3, 5, [], 1.0) and q["resources"] == {}


def test_province_jobs_sums_worker_counts():
    import province

    assert province.province_jobs({}) == 0
    assert province.province_jobs(None) == 0
    assert province.province_jobs({"farms": 2, "not_a_building": 9}) == 100_000
    assert province.province_jobs({"farms": 1, "primary_school": 1}) == 80_000
