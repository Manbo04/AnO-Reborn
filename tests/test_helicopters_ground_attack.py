"""Attack helicopters can join a Ground Invasion (they hit ground troops) but
never defend one."""
from attack_scripts.combat_helpers import compute_unit_casualties
from attack_scripts.Nations import Military
from wars.action_points import parse_one_screen_attack


class _Rng:
    def uniform(self, a, b):
        return b


def test_helicopters_can_be_sent_on_ground_but_not_defend():
    assert "apaches" in Military.ATTACK_UNITS["ground"]
    assert "apaches" in Military.ATTACK_UNITS["air"]
    assert "apaches" not in Military.UNIT_DOMAINS["ground"]
    assert Military.ATTACK_UNITS["naval"] == Military.UNIT_DOMAINS["naval"]


def test_extra_attacker_unit_still_takes_casualties():
    winner_list = ["soldiers", "tanks", "artillery", "apaches"]
    loser_list = ["soldiers", "tanks", "artillery"]
    sent = {u: 100 for u in winner_list}
    w, l = compute_unit_casualties(1, 1, winner_list, loser_list, sent, {u: 100 for u in loser_list}, rng=_Rng())
    assert "apaches" in dict(w)
    assert len(l) == 3


def test_one_screen_ground_attack_reads_ground_apaches():
    owned = {"soldiers": 10, "tanks": 10, "artillery": 10, "apaches": 10}
    parsed, err = parse_one_screen_attack(
        {"attack_type": "ground", "soldiers": "1", "ground_apaches": "4", "apaches": "0"}, owned
    )
    assert err is None
    assert parsed["units"]["apaches"] == 4
