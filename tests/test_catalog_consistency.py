"""Every unit / resource / building must be wired up everywhere it is used.

New content kept shipping half-done: sam_batteries got no spyinfo column
(spy ops 500'd, 2026-09-29) and no military-page buy card; drones/missiles
had no launch UI for a month; a hardcoded resource list missed silver
(country page 500, fixed 2026-10-06). These checks make "add it to the
catalog but forget a place" fail CI instead of failing players.

Units/resources/buildings come from variables.py (the game's catalog); the
database side is the production schema snapshot loaded in CI.
"""
import pytest

import variables
from database import get_db_connection
from game_ui import BUILDING_LEGACY_IMAGES, RESOURCE_LEGACY_IMAGES, UNIT_LEGACY_IMAGES

pytestmark = pytest.mark.no_server

# Units that don't fight in a ground/naval/air domain on purpose.
NON_DOMAIN_UNITS = {"spies", "icbms", "nukes", "sam_batteries"}
# Units with their own code paths (not in variables.UNITS, so not in spy
# reports / generic unit loops). Still checked for a DB row and an image.
SPECIAL_UNITS = {"aircraft_carriers", "counter_intel_agents", "cruise_missiles", "kamikaze_drones"}
# Priced purchases that aren't buildings.
NON_BUILDING_PURCHASES = {"cityCount", "land"}
# Known gaps -- may only shrink. food_banks shows the generic province photo
# until it gets real art (new content needs a real HQ image, not a stand-in).
BUILDINGS_WITHOUT_IMAGE = {"food_banks"}


def _names(table, column="name"):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(f"SELECT {column} FROM {table}")
        return {r[0] for r in db.fetchall()}


def _columns(table):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        return {r[0] for r in db.fetchall()}


def test_units_are_fully_wired():
    from attack_scripts.Nations import Military

    in_db = _names("unit_dictionary")
    spy_cols = _columns("spyinfo")
    domain_units = {u for us in Military.UNIT_DOMAINS.values() for u in us}
    problems = []
    for unit in variables.UNITS:
        if unit not in in_db:
            problems.append(f"{unit}: no unit_dictionary row (add it in a migration)")
        if unit not in spy_cols:
            problems.append(f"{unit}: no spyinfo column (spy reports UPDATE it -> 500)")
        if unit not in UNIT_LEGACY_IMAGES:
            problems.append(f"{unit}: no image in game_ui.UNIT_LEGACY_IMAGES")
        if unit not in domain_units and unit not in NON_DOMAIN_UNITS:
            problems.append(f"{unit}: in no Military.UNIT_DOMAINS domain (or add to NON_DOMAIN_UNITS)")
    assert not problems, "\n".join(problems)


def test_resources_are_fully_wired():
    in_db = _names("resource_dictionary")
    spy_cols = _columns("spyinfo")
    problems = []
    for res in variables.RESOURCES:
        if res not in in_db:
            problems.append(f"{res}: no resource_dictionary row")
        if res not in spy_cols:
            problems.append(f"{res}: no spyinfo column (spy reports UPDATE it -> 500)")
        if res not in RESOURCE_LEGACY_IMAGES:
            problems.append(f"{res}: no image in game_ui.RESOURCE_LEGACY_IMAGES")
    assert not problems, "\n".join(problems)


def test_buildings_are_fully_wired():
    in_db = _names("building_dictionary")
    priced = {k[: -len("_price")] for k in variables.PROVINCE_UNIT_PRICES if k.endswith("_price")}
    problems = []
    for b in sorted(in_db):
        if b not in priced:
            problems.append(f"{b}: in building_dictionary but no PROVINCE_UNIT_PRICES['{b}_price']")
        if b not in BUILDING_LEGACY_IMAGES and b not in BUILDINGS_WITHOUT_IMAGE:
            problems.append(f"{b}: no image in game_ui.BUILDING_LEGACY_IMAGES")
    for b in sorted(BUILDINGS_WITHOUT_IMAGE & set(BUILDING_LEGACY_IMAGES)):
        problems.append(f"{b}: has an image now -- remove it from BUILDINGS_WITHOUT_IMAGE")
    for b in sorted(priced - in_db - NON_BUILDING_PURCHASES):
        problems.append(f"{b}: priced in PROVINCE_UNIT_PRICES but no building_dictionary row")
    assert not problems, "\n".join(problems)


def test_db_catalogs_have_no_unknown_entries():
    """Rows in the DB catalogs that the code's catalog doesn't know about."""
    problems = []
    in_db = _names("unit_dictionary")
    for unit in sorted(in_db - set(variables.UNITS) - SPECIAL_UNITS):
        problems.append(f"unit_dictionary.{unit}: not in variables.UNITS (or SPECIAL_UNITS)")
    for unit in sorted(SPECIAL_UNITS):
        if unit not in in_db:
            problems.append(f"{unit}: SPECIAL_UNITS entry with no unit_dictionary row")
        if unit not in UNIT_LEGACY_IMAGES:
            problems.append(f"{unit}: no image in game_ui.UNIT_LEGACY_IMAGES")
    for res in sorted(_names("resource_dictionary") - set(variables.RESOURCES)):
        problems.append(f"resource_dictionary.{res}: not in variables.RESOURCES")
    assert not problems, "\n".join(problems)
