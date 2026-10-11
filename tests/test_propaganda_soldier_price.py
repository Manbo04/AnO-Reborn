"""Widespread Propaganda: soldiers cost 35% less to recruit (the military page
always showed it; the purchase used to charge full price)."""
from app_core.military import services


def test_propaganda_discounts_soldiers_only(monkeypatch):
    monkeypatch.setattr(services, "get_upgrades", lambda cId, db=None: {"widespreadpropaganda": True})
    assert services._unit_gold_price(1, "soldiers", 100, None) == 65
    assert services._unit_gold_price(1, "tanks", 100, None) == 100


def test_no_discount_without_tech(monkeypatch):
    monkeypatch.setattr(services, "get_upgrades", lambda cId, db=None: {"widespreadpropaganda": False})
    assert services._unit_gold_price(1, "soldiers", 100, None) == 100
