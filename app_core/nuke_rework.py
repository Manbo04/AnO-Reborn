"""Nuke rework (feature flag ``nuke_rework``, ships OFF). Design: docs/design/NUKE_REWORK.md.

Phase 1: the Nuclear Weapons Facility manufactures nukes into the shared unit
stockpile; capacity is one nuke per silo (owned + stockpiled); activation costs
gold (MILDICT price). Direct purchase of ``nukes`` is closed while the flag is on.
"""
from app_core.feature_flags import is_on

FLAG = "nuke_rework"
FACILITY = "nuclear_weapons_facility"
UNIT = "nukes"
HOURS_PER_MISSILE = 72
# Resources consumed per manufactured nuke (same as the old direct-buy resources).
MISSILE_RESOURCES = {"aluminium": 120000, "components": 100000, "gasoline": 25000, "uranium": 20000}
MISSILES_PER_SILO = 1
HIDDEN = frozenset({FACILITY})


def enabled(user_id=None) -> bool:
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def is_hidden(name) -> bool:
    return name in HIDDEN and not enabled()


def activatable(unit, user_id=None) -> bool:
    """True when ``unit`` is the nuke and the rework routes it via the stockpile."""
    return unit == UNIT and enabled(user_id)


def capacity(db, user_id) -> int:
    """Max nukes a nation may hold (owned + stockpiled): silos x MISSILES_PER_SILO."""
    db.execute(
        "SELECT COALESCE(SUM(ub.quantity),0) FROM user_buildings ub "
        "JOIN building_dictionary bd ON bd.building_id=ub.building_id "
        "WHERE ub.user_id=%s AND bd.name='silos'",
        (user_id,),
    )
    return int(db.fetchone()[0] or 0) * MISSILES_PER_SILO


def status(db, user_id) -> dict:
    """Numbers the Military page shows: capacity, stockpile, owned, progress, auto flag."""
    db.execute("SELECT unit_id FROM unit_dictionary WHERE name=%s", (UNIT,))
    r = db.fetchone()
    uid = r[0] if r else None
    owned = stocked = 0
    if uid:
        db.execute("SELECT COALESCE(quantity,0) FROM user_military WHERE user_id=%s AND unit_id=%s", (user_id, uid))
        r = db.fetchone(); owned = int(r[0]) if r else 0
        db.execute("SELECT COALESCE(quantity,0) FROM user_unit_stockpile WHERE user_id=%s AND unit_id=%s", (user_id, uid))
        r = db.fetchone(); stocked = int(r[0]) if r else 0
    db.execute(
        "SELECT COALESCE(SUM(ub.quantity),0) FROM user_buildings ub JOIN building_dictionary bd "
        "ON bd.building_id=ub.building_id WHERE ub.user_id=%s AND bd.name=%s", (user_id, FACILITY))
    facilities = int(db.fetchone()[0] or 0)
    db.execute("SELECT progress FROM user_nuke_progress WHERE user_id=%s", (user_id,))
    r = db.fetchone(); progress = float(r[0]) if r else 0.0
    db.execute("SELECT auto_missile, auto_retaliate FROM user_nuke_settings WHERE user_id=%s", (user_id,))
    r = db.fetchone(); auto = bool(r[0]) if r else False
    auto_ret = bool(r[1]) if r else False
    return {"owned": owned, "stockpile": stocked, "capacity": capacity(db, user_id), "facilities": facilities,
            "progress": progress, "auto": auto, "auto_retaliate": auto_ret, "hours_per_missile": HOURS_PER_MISSILE,
            "resources": MISSILE_RESOURCES}
