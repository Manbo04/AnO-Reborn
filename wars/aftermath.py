"""Battle aftermath (population/war rebalance, 2026-10-04, agreed with
The_kaiser in staff-chat).

Before this, a won battle never touched the loser's population (a nation
with 80 provinces shrugged off everything), and an air attack could only
ever fight air units, so bombers never killed a single soldier. Now:

* **Civilian deaths.** A won ground or bomber attack kills a share of the
  enemy's WHOLE nation (spread over every province), so spreading people
  over many provinces doesn't dilute it.
* **Growth freeze.** Whoever loses a battle gets no population growth for
  LOSS_FREEZE_HOURS (population_growth_freezes, migration 0106). A nuke
  freezes the target for NUKE_FREEZE_HOURS.
* **Bomber ground strike.** If an air attack with bombers wins, the bombers
  also hit the defender's soldiers and tanks (the counter table always said
  bombers beat soldiers/tanks), capped per bomber so one bomber can't wipe
  out an army.

Pure math is at the top (unit-tested); the DB helpers take a cursor and
never commit, the caller does.
"""

from __future__ import annotations

WIN_LEVELS = {"close victory": 1, "definite victory": 2, "annihilation": 3}

# Share of the defender's total population killed by a won attack.
CIVILIAN_DEATHS = {
    "ground": {1: 0.001, 2: 0.002, 3: 0.003},
    "bombers": {1: 0.002, 2: 0.004, 3: 0.006},
}

# Share of the defender's soldiers/tanks destroyed by a won bomber attack,
# capped at BOMBER_KILL_CAP units per surviving bomber.
BOMBER_GROUND_LOSS = {1: 0.05, 2: 0.10, 3: 0.15}
BOMBER_KILL_CAP = {"soldiers": 25, "tanks": 2}

LOSS_FREEZE_HOURS = 12
NUKE_FREEZE_HOURS = 24
NUKE_FALLOUT_DEATHS = 0.01  # whole target nation


def win_level(win_condition) -> int:
    return WIN_LEVELS.get(str(win_condition or "").strip().lower(), 1)


def civilian_death_pct(domain, attacker_units, win_condition) -> float:
    """Share of the defender's population killed by a WON attack."""
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
    wars/nuclear.py), the education split is scaled here. Returns deaths."""
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
    return int(db.fetchone()[0] or 0)


def freeze_growth(db, user_id, hours, reason) -> None:
    """No population growth for this nation for `hours` (extends, never
    shortens, an existing freeze)."""
    db.execute(
        """
        INSERT INTO population_growth_freezes (user_id, frozen_until, reason)
        VALUES (%s, now() + make_interval(hours => %s), %s)
        ON CONFLICT (user_id) DO UPDATE SET
            frozen_until = GREATEST(population_growth_freezes.frozen_until,
                                    EXCLUDED.frozen_until),
            reason = EXCLUDED.reason
        """,
        (user_id, int(hours), reason),
    )


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
    win_condition,
) -> dict:
    """Everything a resolved battle does to population/ground units on top
    of the normal fight. Returns a summary for the battle report/news."""
    summary = {"civilian_deaths": 0, "bomber_ground_losses": {}, "frozen": None}
    loser = defender_id if attacker_won else attacker_id
    freeze_growth(db, loser, LOSS_FREEZE_HOURS, "lost a battle")
    summary["frozen"] = loser
    if not attacker_won:
        return summary
    pct = civilian_death_pct(domain, attacker_units, win_condition)
    summary["civilian_deaths"] = kill_civilians(db, defender_id, pct)
    if domain == "air":
        bombers = int((attacker_units or {}).get("bombers") or 0)
        losses = bomber_ground_losses(
            bombers, read_ground_army(db, defender_id), win_condition
        )
        apply_unit_losses(db, defender_id, losses)
        summary["bomber_ground_losses"] = losses
    return summary
