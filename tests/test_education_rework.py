import pytest
from app_core.game_ticks.population import calc_education_graduation
from variables import POLICY_MANDATORY_SCHOOLING, DEMO_AGING_RATES

def test_education_tier_chaining():
    # 1000 can graduate
    pop_children = int(1000 / DEMO_AGING_RATES["children_to_working"])
    
    # 1000 pass primary (2 buildings)
    # 500 pass HS (1 building)
    # 250 pass uni (0.5 building -> effectively 0 if int, let's say 1 building but we want to see it cap)
    # 2 primary, 1 HS, 0 Uni
    stats = calc_education_graduation(pop_children, [], 2, 1, 0)
    
    assert stats["can_graduate"] == 1000
    assert stats["passed_primary"] == 1000
    assert stats["passed_hs"] == 500
    assert stats["passed_uni"] == 0
    assert stats["edu_college_new"] == 0
    assert stats["edu_highschool_new"] == 500
    assert stats["edu_none_new"] == 500
    
    # 1 primary, 2 HS, 2 Uni
    # Only 500 can pass primary, so even with 1000 HS capacity, only 500 pass HS
    stats2 = calc_education_graduation(pop_children, [], 1, 2, 2)
    assert stats2["passed_primary"] == 500
    assert stats2["passed_hs"] == 500
    assert stats2["passed_uni"] == 500
    assert stats2["edu_college_new"] == 500
    assert stats2["edu_highschool_new"] == 0
    assert stats2["edu_none_new"] == 500

