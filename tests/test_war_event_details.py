import pytest

pytestmark = pytest.mark.no_server

from types import SimpleNamespace

from attack_scripts.war_orchestrator import _fight_details


def test_fight_details_records_units_and_strengths():
    attacker = SimpleNamespace(selected_units={"soldiers": 46000, "tanks": 0})
    defender = SimpleNamespace(selected_units={"soldiers": 11861})
    d = _fight_details(attacker, defender, False, 3, 100.0, 99.0, 50.0, 40.0)
    assert d["attacker_won"] is True
    assert d["winner_units"] == {"soldiers": 46000, "tanks": 0}
    assert d["loser_units"] == {"soldiers": 11861}
    assert d["winner_strength"] == [100.0, 99.0]
    assert d["loser_strength"] == [50.0, 40.0]


def test_fight_details_tolerates_missing_units():
    d = _fight_details(SimpleNamespace(), SimpleNamespace(selected_units=None), True, None, 1, 1, 1, 1)
    assert d["attacker_won"] is False
    assert d["winner_units"] == {} and d["loser_units"] == {}
