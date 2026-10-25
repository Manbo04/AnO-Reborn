"""Pure rules of the war rules overhaul (wars/rules.py); no DB needed."""
import pytest

from wars import rules

pytestmark = pytest.mark.no_server


def test_minimum_war_duration():
    now = 1_000_000.0
    assert not rules.war_age_ok(now - 600, now)  # 10 minutes: too soon
    assert rules.war_age_ok(now - rules.WAR_MIN_DURATION_SECONDS, now)
    assert "24 hours" in rules.min_duration_error(now - 600, now)


def test_post_war_cooldowns():
    # A declared on B: A is the aggressor (truce), B the defender (cooldown).
    assert rules.post_war_lock_seconds(1, 1, 2, "declared") == rules.TRUCE_SECONDS
    assert rules.post_war_lock_seconds(2, 1, 2, "declared") == rules.DEFENDER_COOLDOWN_SECONDS
    assert 0 < rules.DEFENDER_COOLDOWN_SECONDS <= rules.TRUCE_SECONDS


def test_mdp_join_is_not_an_offensive_war():
    # Ally 3 joined against aggressor 1 (row attacker=3, defender=1).
    assert rules.aggressor_of(3, 1, rules.WAR_ORIGIN_MDP_JOIN) == 1
    assert rules.aggressor_of(3, 1, rules.WAR_ORIGIN_DECLARED) == 3
    # The ally only gets the defender cooldown afterwards, not the truce.
    assert (
        rules.post_war_lock_seconds(3, 3, 1, rules.WAR_ORIGIN_MDP_JOIN)
        == rules.DEFENDER_COOLDOWN_SECONDS
    )
    assert rules.post_war_lock_seconds(1, 3, 1, rules.WAR_ORIGIN_MDP_JOIN) == rules.TRUCE_SECONDS


def test_surrender_spoils_and_cap():
    assert rules.surrender_spoils_rate("conditional", 0.2) == rules.CONDITIONAL_SURRENDER_SPOILS
    assert rules.surrender_spoils_rate("unconditional", 0.2) == 0.2
    assert rules.surrender_spoils_rate(None, 0.3) == 0.3
    assert rules.penalized_manpower_cap(1000, []) == 1000
    assert rules.penalized_manpower_cap(1000, [0.5]) == 500
    assert rules.penalized_manpower_cap(1000, [0.5, 0.8]) == 500  # no stacking


def test_nuke_rules():
    assert rules.MAX_NUKE_VOLLEYS_PER_WAR == 1
    assert rules.RADIATION_DAMAGE_MULTIPLIER == 0.5
    assert rules.nuke_column(7, 7) == "attacker_nuked"
    assert rules.nuke_column(7, 8) == "defender_nuked"
