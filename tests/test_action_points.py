import pytest
from wars import action_points

pytestmark = pytest.mark.no_server


def test_ap_constants():
    assert action_points.AP_MAX == 12
    assert action_points.AP_START == 6
    assert action_points.AP_REGEN_PER_HOUR == 1
    assert action_points.ENTRENCH_MAX == 3
    assert action_points.INTEL_MAX == 100


def test_get_ap_cost():
    assert action_points.get_ap_cost("ground_attack") == ("ground", 3)
    assert action_points.get_ap_cost("air_attack") == ("air", 3)
    assert action_points.get_ap_cost("naval_attack") == ("naval", 3)
    assert action_points.get_ap_cost("drone_strike") == ("air", 2)
    assert action_points.get_ap_cost("cruise_missile_strike") == ("naval", 2)
    assert action_points.get_ap_cost("dig_in") == ("ground", 2)
    assert action_points.get_ap_cost("recon_flight") == ("air", 2)
    assert action_points.get_ap_cost("nuke") == (None, 0)
    assert action_points.get_ap_cost("strategic_airstrike") == (None, 0)
    assert action_points.get_ap_cost("unknown_action") == (None, 0)


def test_clamp_ap():
    assert action_points.clamp_ap(6, 1) == 7
    assert action_points.clamp_ap(11, 1) == 12
    assert action_points.clamp_ap(12, 1) == 12
    assert action_points.clamp_ap(15, 1) == 12
    assert action_points.clamp_ap(0, 0) == 0
    assert action_points.clamp_ap(None, 1) == 1


def test_can_spend_ap():
    assert action_points.can_spend_ap(6, 3) is True
    assert action_points.can_spend_ap(3, 3) is True
    assert action_points.can_spend_ap(2, 3) is False
    assert action_points.can_spend_ap(0, 2) is False
    assert action_points.can_spend_ap(None, 1) is False


def test_entrenchment_defense_multiplier():
    assert action_points.entrenchment_defense_multiplier(0) == 1.0
    assert action_points.entrenchment_defense_multiplier(1) == 1.10
    assert action_points.entrenchment_defense_multiplier(2) == 1.20
    assert action_points.entrenchment_defense_multiplier(3) == 1.30
    # Clamping outside 0..3
    assert action_points.entrenchment_defense_multiplier(4) == 1.30
    assert action_points.entrenchment_defense_multiplier(-1) == 1.0
    assert action_points.entrenchment_defense_multiplier(None) == 1.0


def test_intel_attack_multiplier():
    assert action_points.intel_attack_multiplier(0) == 1.0
    # +intel/10 % attack strength -> 25 intel gives +2.5% = 1.025
    assert action_points.intel_attack_multiplier(25) == 1.025
    assert action_points.intel_attack_multiplier(50) == 1.05
    assert action_points.intel_attack_multiplier(100) == 1.10
    # Clamping above 100
    assert action_points.intel_attack_multiplier(150) == 1.10
    assert action_points.intel_attack_multiplier(-10) == 1.0
    assert action_points.intel_attack_multiplier(None) == 1.0


def test_parse_one_screen_attack_domain():
    owned = {"soldiers": 100, "tanks": 50, "artillery": 20}
    form = {
        "attack_type": "ground",
        "soldiers": "50",
        "tanks": "10",
        "artillery": "5",
    }
    payload, err = action_points.parse_one_screen_attack(form, owned)
    assert err is None
    assert payload is not None
    assert payload["domain"] == "ground"
    assert payload["units"] == {"soldiers": 50, "tanks": 10, "artillery": 5}
    assert payload["ap_branch"] == "ground"
    assert payload["ap_cost"] == 3


def test_parse_one_screen_attack_insufficient_units():
    owned = {"soldiers": 10, "tanks": 0, "artillery": 0}
    form = {
        "attack_type": "ground",
        "soldiers": "50",
        "tanks": "0",
        "artillery": "0",
    }
    payload, err = action_points.parse_one_screen_attack(form, owned)
    assert payload is None
    assert "You only own 10 soldiers" in err


def test_parse_one_screen_attack_insufficient_ap():
    owned = {"fighters": 10, "bombers": 5, "apaches": 2}
    form = {
        "attack_type": "air",
        "fighters": "5",
        "bombers": "2",
        "apaches": "0",
    }
    current_ap = {"air": 1, "ground": 6, "naval": 6}
    payload, err = action_points.parse_one_screen_attack(form, owned, current_ap=current_ap)
    assert payload is None
    assert "Not enough air action points (have 1, need 3)" in err


def test_parse_one_screen_attack_special():
    owned = {"icbms": 5}
    form = {
        "attack_type": "special",
        "special_unit": "icbms",
        "amount": "2",
        "targeted_unit": "tanks",
    }
    payload, err = action_points.parse_one_screen_attack(form, owned)
    assert err is None
    assert payload is not None
    assert payload["special"] is True
    assert payload["unit"] == "icbms"
    assert payload["amount"] == 2
    assert payload["target"] == "tanks"


def test_parse_one_screen_attack_nukes():
    owned = {"nukes": 1}
    form = {
        "attack_type": "special",
        "special_unit": "nukes",
    }
    payload, err = action_points.parse_one_screen_attack(form, owned)
    assert err is None
    assert payload is not None
    assert payload["is_nuke"] is True


def test_apply_combat_modifiers_ground_entrenchment():
    from attack_scripts.combat_helpers import apply_combat_modifiers

    # Entrenchment level 2 (+20%) on ground battle
    atk_amt, atk_bon, dfn_amt, dfn_bon = apply_combat_modifiers(
        100.0, 50.0, 100.0, 50.0, entrenchment_level=2, attacker_intel=0, is_ground=True
    )
    assert atk_amt == 100.0
    assert atk_bon == 50.0
    assert pytest.approx(dfn_amt, 0.001) == 120.0
    assert pytest.approx(dfn_bon, 0.001) == 60.0


def test_apply_combat_modifiers_non_ground_ignores_entrenchment():
    from attack_scripts.combat_helpers import apply_combat_modifiers

    # Entrenchment level 3 should NOT apply on air/naval battle
    atk_amt, atk_bon, dfn_amt, dfn_bon = apply_combat_modifiers(
        100.0, 50.0, 100.0, 50.0, entrenchment_level=3, attacker_intel=0, is_ground=False
    )
    assert atk_amt == 100.0
    assert atk_bon == 50.0
    assert dfn_amt == 100.0
    assert dfn_bon == 50.0


def test_apply_combat_modifiers_intel():
    from attack_scripts.combat_helpers import apply_combat_modifiers

    # Intel 50 gives +5% to attacker
    atk_amt, atk_bon, dfn_amt, dfn_bon = apply_combat_modifiers(
        100.0, 50.0, 100.0, 50.0, entrenchment_level=0, attacker_intel=50, is_ground=True
    )
    assert pytest.approx(atk_amt, 0.001) == 105.0
    assert pytest.approx(atk_bon, 0.001) == 52.5
    assert dfn_amt == 100.0
    assert dfn_bon == 50.0

