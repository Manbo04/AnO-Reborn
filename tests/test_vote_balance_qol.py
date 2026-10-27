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
    assert "Employs 50,000 workers" in text and "upkeep" in text
    assert building_info_text("not_a_building") == ""
    assert enrich_building_row({"name": "farms", "display_name": "Farms"})["info"] == text
