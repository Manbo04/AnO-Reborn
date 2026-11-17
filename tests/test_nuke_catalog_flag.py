"""The province page catalog only lists the Nuclear Weapons Facility while nuke_rework is on."""
from pathlib import Path

from jinja2 import Environment

CATALOG = Path(__file__).resolve().parent.parent / "templates" / "partials" / "province_catalog.html"


def _units(flag_on: bool) -> list[str]:
    env = Environment()
    env.globals.update(
        nuke_rework_on=lambda *a: flag_on,
        ledger_goods_on=lambda *a: True,
        ledger_goods_buildings=[],
    )
    src = CATALOG.read_text() + "\n{{ PROVINCE_CATALOG | map(attribute='unit') | join(',') }}"
    return env.from_string(src).render().strip().splitlines()[-1].split(",")


def test_facility_listed_only_when_flag_on():
    assert "nuclear_weapons_facility" in _units(True)
    assert "nuclear_weapons_facility" not in _units(False)
    assert "silos" in _units(False)  # the rest of the military group is untouched
