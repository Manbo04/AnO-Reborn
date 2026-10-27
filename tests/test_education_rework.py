from app_core.game_ticks.population import calc_education_graduation
from variables import DEMO_AGING_RATES

# Capacities come from variables (weekly vote 10-16: 5,000 / 10,000 / 40,000).
import variables

P = variables.PRIMARY_SCHOOL_CAPACITY
H = variables.HIGH_SCHOOL_CAPACITY
U = variables.UNIVERSITY_CAPACITY
CAN = 2 * H  # graduating cohort per tick, bigger than one high school


def _children():
    return int(CAN / DEMO_AGING_RATES["children_to_working"])


def test_education_tier_chaining(monkeypatch):
    monkeypatch.setattr(variables, "EDUCATION_CHAIN_GRACE_UNTIL", "")
    pop_children = _children()

    # Plenty of primary schools, one HS, no university: the HS caps the chain.
    stats = calc_education_graduation(pop_children, [], CAN // P + 1, 1, 0)

    assert stats["can_graduate"] == CAN
    assert stats["passed_primary"] == CAN
    assert stats["passed_hs"] == H  # one HS = H places (mechanics page)
    assert stats["passed_uni"] == 0
    assert stats["edu_college_new"] == 0
    assert stats["edu_highschool_new"] == H
    assert stats["edu_none_new"] == CAN - H

    # With a university too, the HS graduates move on to college.
    stats2 = calc_education_graduation(pop_children, [], CAN // P + 1, 1, 1)
    assert stats2["passed_primary"] == CAN
    assert stats2["passed_hs"] == H
    assert stats2["passed_uni"] == min(H, U)
    assert stats2["edu_college_new"] == min(H, U)
    assert stats2["edu_highschool_new"] == H - min(H, U)
    assert stats2["edu_none_new"] == CAN - H

    # A high school needs two primary schools feeding it to fill up.
    one_primary = calc_education_graduation(pop_children, [], 1, 1, 0)
    assert one_primary["passed_hs"] == P
    two_primary = calc_education_graduation(pop_children, [], 2, 1, 0)
    assert two_primary["passed_hs"] == H


def test_education_grace_period():
    from datetime import datetime, timezone

    variables.EDUCATION_CHAIN_GRACE_UNTIL = "2026-10-05T00:00:00+00:00"
    pop_children = _children()

    # During grace period: 0 primary, 1 HS, 1 Uni; primary capacity acts as
    # max(0, HS + Uni) so higher tiers still work.
    grace_time = datetime(2026, 10, 4, tzinfo=timezone.utc)
    stats_grace = calc_education_graduation(pop_children, [], 0, 1, 1, now=grace_time)

    assert stats_grace["passed_primary"] == CAN
    assert stats_grace["passed_hs"] == H
    assert stats_grace["passed_uni"] == min(H, U)
    assert stats_grace["true_primary_capacity"] == 0

    # After grace period: strict chain
    after_grace = datetime(2026, 10, 5, 0, 0, 1, tzinfo=timezone.utc)
    stats_after = calc_education_graduation(pop_children, [], 0, 1, 1, now=after_grace)

    assert stats_after["passed_primary"] == 0
    assert stats_after["passed_hs"] == 0
    assert stats_after["passed_uni"] == 0
    assert stats_after["edu_college_new"] == 0
    assert stats_after["edu_highschool_new"] == 0
    assert stats_after["edu_none_new"] == CAN
