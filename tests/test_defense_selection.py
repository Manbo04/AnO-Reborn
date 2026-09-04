"""Regression tests for defender combat composition (Bug B fix).

Combat used to always auto-pick the defender's top-3-owned-by-quantity unit
types, completely ignoring a player's saved `/defense` choice (`stats.default_defense`).
`resolve_defender_composition` in `attack_scripts/war_orchestrator.py` is the fix:
it prefers the saved choice and only falls back to the auto-pick when no valid
choice has been saved.
"""

import uuid
import datetime

from database import get_db_connection
from attack_scripts.war_orchestrator import resolve_defender_composition


def _make_test_user(db):
    username = f"deftest{uuid.uuid4().hex[:6]}"
    db.execute(
        "INSERT INTO users (username,email,date,hash,auth_type) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (username, f"{username}@example.test", str(datetime.date.today()), "x", "normal"),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (uid, "T"),
    )
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT %s, unit_id, 0 FROM unit_dictionary WHERE is_active = TRUE "
        "ON CONFLICT DO NOTHING",
        (uid,),
    )
    return uid


def _set_quantity(db, uid, unit_name, quantity):
    db.execute(
        "UPDATE user_military um SET quantity=%s FROM unit_dictionary ud "
        "WHERE um.unit_id=ud.unit_id AND um.user_id=%s AND LOWER(ud.name)=LOWER(%s)",
        (quantity, uid, unit_name),
    )


def _cleanup(db, conn, uid):
    db.execute("DELETE FROM user_military WHERE user_id=%s", (uid,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid,))
    db.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()


def test_resolve_defender_composition_falls_back_to_top3_by_quantity():
    # Player never configured /defense -> preserve legacy auto-pick behaviour.
    with get_db_connection() as conn:
        db = conn.cursor()
        uid = _make_test_user(db)
        _set_quantity(db, uid, "soldiers", 5)
        _set_quantity(db, uid, "tanks", 500)
        _set_quantity(db, uid, "artillery", 300)
        _set_quantity(db, uid, "apaches", 200)
        conn.commit()

        try:
            defenselst, defenseunits = resolve_defender_composition(uid)
            assert set(defenselst) == {"tanks", "artillery", "apaches"}
            assert "soldiers" not in defenselst
            assert defenseunits["tanks"] == 500
        finally:
            _cleanup(db, conn, uid)


def test_resolve_defender_composition_honors_saved_defense_choice():
    # Player configured /defense with soldiers among their picks -> soldiers
    # must be defendable even though they aren't the top-3-owned types.
    from attack_scripts.Nations import Military

    with get_db_connection() as conn:
        db = conn.cursor()
        uid = _make_test_user(db)
        _set_quantity(db, uid, "soldiers", 5)
        _set_quantity(db, uid, "tanks", 500)
        _set_quantity(db, uid, "artillery", 300)
        _set_quantity(db, uid, "apaches", 200)
        conn.commit()

        try:
            Military(uid).set_defense("soldiers,apaches,cruisers")

            defenselst, defenseunits = resolve_defender_composition(uid)
            assert set(defenselst) == {"soldiers", "apaches", "cruisers"}
            assert defenseunits["soldiers"] == 5
        finally:
            _cleanup(db, conn, uid)


def test_resolve_defender_composition_restricts_to_attacked_domain():
    # A naval attack must be met with naval units only, regardless of any
    # saved /defense choice or top-owned quantities in other domains — a
    # destroyer can't be called up to defend against tanks it can't reach.
    from attack_scripts.Nations import Military

    with get_db_connection() as conn:
        db = conn.cursor()
        uid = _make_test_user(db)
        _set_quantity(db, uid, "tanks", 500)
        _set_quantity(db, uid, "destroyers", 5)
        _set_quantity(db, uid, "cruisers", 10)
        _set_quantity(db, uid, "submarines", 15)
        conn.commit()

        try:
            # Saved defense picks a mixed/ground composition — must be
            # ignored once a domain is supplied.
            Military(uid).set_defense("soldiers,tanks,apaches")

            defenselst, defenseunits = resolve_defender_composition(uid, "naval")
            assert set(defenselst) == {"destroyers", "cruisers", "submarines"}
            assert defenseunits["destroyers"] == 5
            assert defenseunits["cruisers"] == 10
            assert defenseunits["submarines"] == 15
            assert "tanks" not in defenseunits
        finally:
            _cleanup(db, conn, uid)


def test_resolve_defender_composition_ground_domain_ignores_top_owned():
    # Even if the defender's biggest stockpile is naval/air, a ground attack
    # can only be met with ground units.
    from attack_scripts.Nations import Military

    with get_db_connection() as conn:
        db = conn.cursor()
        uid = _make_test_user(db)
        _set_quantity(db, uid, "soldiers", 1)
        _set_quantity(db, uid, "tanks", 2)
        _set_quantity(db, uid, "artillery", 3)
        _set_quantity(db, uid, "destroyers", 9000)
        conn.commit()

        try:
            defenselst, defenseunits = resolve_defender_composition(uid, "ground")
            assert set(defenselst) == {"soldiers", "tanks", "artillery"}
            assert defenseunits == {"soldiers": 1, "tanks": 2, "artillery": 3}
        finally:
            _cleanup(db, conn, uid)
