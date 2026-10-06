"""Mass purchase and /province share one power calculation (ieb, 2026-10-06:
mass purchase flagged provinces "Blackout" that /province showed as powered)."""

from app_core.economy.province_energy import province_energy

NO_UPGRADES = {"betterengineering": False, "electricarcfurnace": False}
RICH = 10**12


def test_productivity_bonus_counts_toward_power():
    # 10 solar fields = 30 base energy; 145% productivity -> 44 >= 40 used.
    units = {"solar_fields": 10, "general_stores": 40}
    assert province_energy(units, NO_UPGRADES, 100, 1.0, RICH, {})["has_power"]
    assert not province_energy(units, NO_UPGRADES, 50, 1.0, RICH, {})["has_power"]


def test_better_engineering_reactor_bonus():
    units = {"nuclear_reactors": 1, "general_stores": 21}
    econ = {"uranium": 1000}
    assert not province_energy(units, NO_UPGRADES, 50, 1.0, RICH, econ)["has_power"]
    upgraded = {**NO_UPGRADES, "betterengineering": True}
    assert province_energy(units, upgraded, 50, 1.0, RICH, econ)["has_power"]


def test_unaffordable_plants_do_not_power():
    units = {"solar_fields": 10, "general_stores": 20}
    assert not province_energy(units, NO_UPGRADES, 50, 1.0, 0, {})["has_power"]


def test_eaf_steel_mills_use_two_energy():
    units = {"wind_farms": 5, "steel_mills": 6}
    assert province_energy(units, NO_UPGRADES, 50, 1.0, RICH, {})["has_power"]
    eaf = {**NO_UPGRADES, "electricarcfurnace": True}
    assert not province_energy(units, eaf, 50, 1.0, RICH, {})["has_power"]
