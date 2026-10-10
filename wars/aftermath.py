"""Battle aftermath (population/war rebalance).

* **Civilian deaths.** A won ground or bomber attack kills a share of the
  attacked province's population (ground 1%/2%/3%, bombers 2%/4%/6% for
  close/definite/annihilation victory).
* **No growth freeze.** Losing a battle or being nuked no longer freezes growth
  (penalty removed per 2026-10-10 community vote).
* **Bomber ground strike.** If an air attack with bombers wins, the bombers
  also hit the defender's soldiers and tanks, capped per bomber.

Pure math is at the top (unit-tested); the DB helpers take a cursor and
never commit, the caller does.
"""

from __future__ import annotations

WIN_LEVELS = {"close victory": 1, "definite victory": 2, "annihilation": 3}

# Share of the attacked province's population killed by a won attack.
CIVILIAN_DEATHS = {
    "ground": {1: 0.01, 2: 0.02, 3: 0.03},
    "bombers": {1: 0.02, 2: 0.04, 3: 0.06},
}

# Share of the defender's soldiers/tanks destroyed by a won bomber attack,
# capped at BOMBER_KILL_CAP units per surviving bomber.
BOMBER_GROUND_LOSS = {1: 0.05, 2: 0.10, 3: 0.15}
BOMBER_KILL_CAP = {"soldiers": 25, "tanks": 2}

NUKE_FALLOUT_DEATHS = 0.01  # whole target nation


def win_level(win_condition) -> int:
    return WIN_LEVELS.get(str(win_condition or "").strip().lower(), 1)


def civilian_death_pct(domain, attacker_units, win_condition) -> float:
    """Share of the attacked province's population killed by a WON attack."""
    level = win_level(win_condition)
    if domain == "air":
        if int((attacker_units or {}).get("bombers") or 0) <= 0:
            return 0.0
        return CIVILIAN_DEATHS["bombers"][level]
    if domain in (None, "ground"):
        return CIVILIAN_DEATHS["ground"][level]
    return 0.0  # naval: ships don't hit cities


def bomber_ground_losses(bombers, defender_ground, win_condition) -> dict:
    """{unit: lost} for a won bomber attack against the defender's ground
    army ({"soldiers": n, "tanks": n})."""
    bombers = max(0, int(bombers or 0))
    if bombers <= 0:
        return {}
    pct = BOMBER_GROUND_LOSS[win_level(win_condition)]
    out = {}
    for unit, per_bomber in BOMBER_KILL_CAP.items():
        owned = max(0, int((defender_ground or {}).get(unit) or 0))
        lost = min(int(owned * pct), bombers * per_bomber)
        if lost > 0:
            out[unit] = lost
    return out


# ---------------------------------------------------------------------------
# DB helpers (cursor in, caller commits)
# ---------------------------------------------------------------------------


def kill_civilians(db, user_id, pct) -> int:
    """Kill `pct` of every province's population for this nation. The age
    split is rescaled by the trg_sync_province_population trigger (see
    wars/nuclear.py), the education split is scaled here. Used by nukes.
    Returns deaths."""
    if pct <= 0:
        return 0
    survive = 1.0 - pct
    db.execute(
        """
        WITH d AS (
            SELECT id, FLOOR(COALESCE(population, 0) * %s)::bigint AS dead
            FROM provinces WHERE userId = %s AND COALESCE(population, 0) > 0
        ), upd AS (
            UPDATE provinces p SET
                population = GREATEST(0, p.population - d.dead),
                edu_none = FLOOR(COALESCE(p.edu_none, 0) * %s),
                edu_highschool = FLOOR(COALESCE(p.edu_highschool, 0) * %s),
                edu_college = FLOOR(COALESCE(p.edu_college, 0) * %s)
            FROM d WHERE p.id = d.id AND d.dead > 0
            RETURNING d.dead
        )
        SELECT COALESCE(SUM(dead), 0) FROM upd
        """,
        (pct, user_id, survive, survive, survive),
    )
    row = db.fetchone()
    return int((row[0] if row else 0) or 0)


def kill_civilians_in_province(db, province_id, pct) -> int:
    """Kill `pct` of the specified province's population. The age split is
    rescaled by the trg_sync_province_population trigger, the education split
    is scaled here. Returns deaths."""
    if not province_id or pct <= 0:
        return 0
    survive = 1.0 - pct
    db.execute(
        """
        WITH d AS (
            SELECT id, FLOOR(COALESCE(population, 0) * %s)::bigint AS dead
            FROM provinces WHERE id = %s AND COALESCE(population, 0) > 0
        ), upd AS (
            UPDATE provinces p SET
                population = GREATEST(0, p.population - d.dead),
                edu_none = FLOOR(COALESCE(p.edu_none, 0) * %s),
                edu_highschool = FLOOR(COALESCE(p.edu_highschool, 0) * %s),
                edu_college = FLOOR(COALESCE(p.edu_college, 0) * %s)
            FROM d WHERE p.id = d.id AND d.dead > 0
            RETURNING d.dead
        )
        SELECT COALESCE(SUM(dead), 0) FROM upd
        """,
        (pct, province_id, survive, survive, survive),
    )
    row = db.fetchone()
    return int((row[0] if row else 0) or 0)


def read_ground_army(db, user_id) -> dict:
    db.execute(
        """
        SELECT ud.name, COALESCE(SUM(um.quantity), 0)
        FROM user_military um JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE um.user_id = %s AND ud.name IN ('soldiers', 'tanks')
        GROUP BY ud.name
        """,
        (user_id,),
    )
    return {name: int(qty or 0) for name, qty in db.fetchall()}


def apply_unit_losses(db, user_id, losses) -> None:
    for unit, lost in (losses or {}).items():
        db.execute(
            """
            UPDATE user_military um SET quantity = GREATEST(0, um.quantity - %s)
            FROM unit_dictionary ud
            WHERE ud.unit_id = um.unit_id AND ud.name = %s AND um.user_id = %s
            """,
            (int(lost), unit, user_id),
        )


def apply_battle_aftermath(
    db, attacker_id, defender_id, attacker_won, domain, attacker_units,
    win_condition, province_id=None,
) -> dict:
    """Everything a resolved battle does to population/ground units on top
    of the normal fight. Returns a summary for the battle report/news."""
    summary = {
        "civilian_deaths": 0,
        "province_id": province_id,
        "province_name": None,
        "bomber_ground_losses": {},
    }
    if not attacker_won:
        return summary
    pct = civilian_death_pct(domain, attacker_units, win_condition)
    if province_id:
        summary["civilian_deaths"] = kill_civilians_in_province(db, province_id, pct)
    if province_id:
        db.execute("SELECT provincename FROM provinces WHERE id = %s", (province_id,))
        prow = db.fetchone()
        if prow:
            summary["province_name"] = prow["provincename"] if isinstance(prow, dict) else prow[0]
    if domain == "air":
        bombers = int((attacker_units or {}).get("bombers") or 0)
        losses = bomber_ground_losses(
            bombers, read_ground_army(db, defender_id), win_condition
        )
        apply_unit_losses(db, defender_id, losses)
        summary["bomber_ground_losses"] = losses
    return summary
