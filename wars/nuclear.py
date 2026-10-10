"""Nuclear strikes (rework agreed with players, 2026-09-27).

A nuke hits ONE province the attacker picks (it used to hit the whole nation:
half the population, zero happiness, 40% of every building). What it does now:

* **Deaths scale with density.** A province's footprint is its land plus its
  cities, each at a nominal area (LAND_KM2 / CITY_KM2). People live much more
  densely in cities than on open land (URBAN_DENSITY_RATIO), and the warhead's
  blast (BLAST_AREA_KM2, ~1,413 km2, a ~21 km radius) is aimed at the urban
  core first, then spills onto the countryside. So more land per city means a
  more dispersed population and fewer deaths, and a huge sprawling province
  loses only a small share -- it is never mostly wiped.
* **Buildings and cities** are destroyed in proportion to how much of the
  province the blast covers (INFRA_LETHALITY).
* **Happiness in the struck province drops hard** (HAPPINESS_HIT points).
* **Fallout (2026-10-04).** Radiation also kills 1% of the target's whole
  nation (wars/aftermath.py).
* **Repeat strikes** on the same province within REPEAT_WINDOW_HOURS do less:
  each earlier strike halves the damage, fading linearly over the 72h window.
* **Influence cost for the launcher.** A first strike costs FIRST_STRIKE_COST
  (50%) of the launcher's current influence; since the cost is taken from the
  already-reduced influence, further launches compound. A retaliation strike
  (the target nuked YOU first in this same war) costs RETALIATION_COST (25%).
  Launching needs MIN_LAUNCH_INFLUENCE (1,000,000) influence, except for a
  retaliation. The penalty is stored in nuclear_strikes and decays to zero
  over the struck province's 7-day recovery timer
  (influence_formula.NUCLEAR_PENALTY_DECAY_DAYS).
* Iron Domes in the struck province may intercept it (migration 0104). Two-step confirmation in the UI. Both sides get news.

Pure math lives in the top half (unit-tested without a DB); the DB flow is
plan_strike() (read-only preview) and execute_strike() (locked, atomic).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from influence_formula import (
    NUCLEAR_PENALTY_DECAY_DAYS,
    influence_subquery_sql,
)

# --- Blast model -----------------------------------------------------------
BLAST_AREA_KM2 = 1413.0  # ~21.2 km radius
LAND_KM2 = 50.0  # nominal area of one land slot
CITY_KM2 = 25.0  # nominal urban area of one city
URBAN_DENSITY_RATIO = 20.0  # people per km2 in cities vs open land
POP_LETHALITY = 0.6  # share of people inside the blast who die
INFRA_LETHALITY = 0.7  # share of buildings/cities inside the blast destroyed
HAPPINESS_HIT = 60  # happiness points lost in the struck province

# --- Repeat strikes --------------------------------------------------------
REPEAT_WINDOW_HOURS = 72
REPEAT_FACTOR = 0.5  # each (fresh) earlier strike halves the damage

# --- Influence cost --------------------------------------------------------
FIRST_STRIKE_COST = 0.50
RETALIATION_COST = 0.25
MIN_LAUNCH_INFLUENCE = 1_000_000
RECOVERY_DAYS = NUCLEAR_PENALTY_DECAY_DAYS


def blast_profile(land: float, cities: float) -> dict:
    """How much of a province one full-strength blast covers and kills."""
    land = max(0.0, float(land or 0))
    cities = max(0.0, float(cities or 0))
    urban_area = cities * CITY_KM2
    rural_area = land * LAND_KM2
    footprint = urban_area + rural_area
    if footprint <= 0:
        return {
            "footprint_km2": 0.0,
            "urban_share": 0.0,
            "urban_hit": 0.0,
            "rural_hit": 0.0,
            "coverage": 0.0,
            "death_frac": 0.0,
            "infra_frac": 0.0,
            "city_frac": 0.0,
        }
    # Blast lands on the urban core first, the rest spills onto open land.
    urban_covered = min(urban_area, BLAST_AREA_KM2)
    rural_covered = min(rural_area, BLAST_AREA_KM2 - urban_covered)
    urban_hit = urban_covered / urban_area if urban_area else 0.0
    rural_hit = rural_covered / rural_area if rural_area else 0.0
    weighted_urban = urban_area * URBAN_DENSITY_RATIO
    urban_share = weighted_urban / (weighted_urban + rural_area)
    hit = urban_share * urban_hit + (1 - urban_share) * rural_hit
    return {
        "footprint_km2": footprint,
        "urban_share": urban_share,
        "urban_hit": urban_hit,
        "rural_hit": rural_hit,
        "coverage": (urban_covered + rural_covered) / footprint,
        "death_frac": POP_LETHALITY * hit,
        "infra_frac": INFRA_LETHALITY * hit,
        "city_frac": INFRA_LETHALITY * urban_hit,
    }


def repeat_multiplier(prior_ages_hours) -> float:
    """Damage multiplier given the ages (hours) of earlier strikes on the
    same province. Each fresh strike halves damage; its weight fades
    linearly to nothing at REPEAT_WINDOW_HOURS."""
    weight = sum(
        max(0.0, 1.0 - max(0.0, float(age)) / REPEAT_WINDOW_HOURS)
        for age in (prior_ages_hours or [])
    )
    return REPEAT_FACTOR ** weight


def influence_cost(current_influence: float, is_retaliation: bool) -> int:
    rate = RETALIATION_COST if is_retaliation else FIRST_STRIKE_COST
    return int(math.floor(max(0.0, float(current_influence or 0)) * rate))


def strike_damage(province: dict, multiplier: float) -> dict:
    """Concrete losses for a province row dict (population, land, citycount,
    happiness) at the given repeat multiplier."""
    profile = blast_profile(province.get("land"), province.get("citycount"))
    pop = int(province.get("population") or 0)
    cities = int(province.get("citycount") or 0)
    happiness = int(province.get("happiness") or 0)
    death_frac = profile["death_frac"] * multiplier
    infra_frac = profile["infra_frac"] * multiplier
    city_frac = profile["city_frac"] * multiplier
    return {
        "profile": profile,
        "multiplier": multiplier,
        "death_frac": death_frac,
        "infra_frac": infra_frac,
        "deaths": int(math.floor(pop * death_frac)),
        "cities_destroyed": int(math.floor(cities * city_frac)),
        "happiness_lost": min(happiness, int(round(HAPPINESS_HIT * multiplier))),
    }


# ---------------------------------------------------------------------------
# DB flow
# ---------------------------------------------------------------------------


class StrikeError(Exception):
    """A strike that can't go ahead; the message is player-facing."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def fresh_influence(db, user_id) -> int:
    """Influence straight from the DB (bypasses the page cache)."""
    db.execute(
        "SELECT inf.influence FROM "
        + influence_subquery_sql("SELECT %s::int")
        + " inf",
        (int(user_id),),
    )
    row = db.fetchone()
    return int(row[0] or 0) if row else 0


def _active_war(db, war_id, attacker_id):
    db.execute(
        "SELECT attacker, defender FROM wars "
        "WHERE id = %s AND peace_date IS NULL AND (attacker = %s OR defender = %s)",
        (war_id, attacker_id, attacker_id),
    )
    row = db.fetchone()
    if not row:
        raise StrikeError("You are not in an active war with that id.", 403)
    return row[1] if row[0] == attacker_id else row[0]


def is_retaliation(db, war_id, attacker_id, enemy_id) -> bool:
    """True when the enemy was the first to use a nuke between these two
    nations in this war (so this launch answers theirs)."""
    db.execute(
        """
        SELECT attacker_id FROM nuclear_strikes
        WHERE war_id = %s
          AND ((attacker_id = %s AND target_id = %s)
            OR (attacker_id = %s AND target_id = %s))
        ORDER BY launched_at ASC, id ASC
        LIMIT 1
        """,
        (war_id, enemy_id, attacker_id, attacker_id, enemy_id),
    )
    row = db.fetchone()
    return bool(row) and row[0] == enemy_id


def _nuke_count(db, user_id) -> int:
    db.execute(
        """
        SELECT COALESCE(SUM(um.quantity), 0) FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE um.user_id = %s AND ud.name = 'nukes'
        """,
        (user_id,),
    )
    row = db.fetchone()
    return int(row[0] or 0) if row else 0


def enemy_provinces(db, enemy_id):
    """Enemy provinces with a full-strength blast preview and repeat decay."""
    db.execute(
        """
        SELECT p.id, p.provincename, COALESCE(p.population, 0),
               COALESCE(p.land, 0), COALESCE(CAST(p.citycount AS INTEGER), 0),
               COALESCE(p.happiness, 0),
               COALESCE((
                   SELECT array_agg(EXTRACT(EPOCH FROM (now() - ns.launched_at)) / 3600.0)
                   FROM nuclear_strikes ns
                   WHERE ns.province_id = p.id
                     AND ns.launched_at > now() - make_interval(hours => %s)
               ), ARRAY[]::numeric[])
        FROM provinces p
        WHERE p.userid = %s
        ORDER BY p.population DESC, p.id
        """,
        (REPEAT_WINDOW_HOURS, enemy_id),
    )
    out = []
    for pid, name, pop, land, cities, happiness, ages in db.fetchall():
        prov = {
            "id": pid,
            "name": name,
            "population": int(pop),
            "land": int(land),
            "citycount": int(cities),
            "happiness": int(happiness),
        }
        prov["recent_strikes"] = len(ages or [])
        prov["damage"] = strike_damage(prov, repeat_multiplier(ages or []))
        out.append(prov)
    return out


def plan_strike(db, attacker_id, war_id, province_id=None) -> dict:
    """Everything the launch pages show. Raises StrikeError when the war is
    invalid; eligibility problems are reported in plan['blocked']."""
    enemy_id = _active_war(db, war_id, attacker_id)
    db.execute("SELECT id, username FROM users WHERE id IN (%s, %s)", (attacker_id, enemy_id))
    names = {r[0]: r[1] for r in db.fetchall()}
    influence = fresh_influence(db, attacker_id)
    retaliation = is_retaliation(db, war_id, attacker_id, enemy_id)
    nukes = _nuke_count(db, attacker_id)
    provinces = enemy_provinces(db, enemy_id)
    blocked = None
    if nukes <= 0:
        blocked = "You don't have any nukes."
    elif not provinces:
        blocked = "The enemy has no provinces to target."
    elif not retaliation and influence < MIN_LAUNCH_INFLUENCE:
        blocked = (
            f"You need at least {MIN_LAUNCH_INFLUENCE:,} influence to launch a "
            f"first strike (you have {influence:,})."
        )
    target = None
    if province_id is not None:
        target = next((p for p in provinces if p["id"] == int(province_id)), None)
        if target is None:
            raise StrikeError("That province doesn't belong to your enemy in this war.", 400)
    cost = influence_cost(influence, retaliation)
    return {
        "war_id": war_id,
        "attacker_id": attacker_id,
        "enemy_id": enemy_id,
        "attacker_name": names.get(attacker_id, "Unknown"),
        "enemy_name": names.get(enemy_id, "Unknown"),
        "influence": influence,
        "is_retaliation": retaliation,
        "cost": cost,
        "cost_rate": RETALIATION_COST if retaliation else FIRST_STRIKE_COST,
        "influence_after": max(0, influence - cost),
        "nukes": nukes,
        "provinces": provinces,
        "target": target,
        "blocked": blocked,
        "min_influence": MIN_LAUNCH_INFLUENCE,
        "recovery_days": RECOVERY_DAYS,
    }


def execute_strike(db, attacker_id, war_id, province_id) -> dict:
    """Launch one nuke. Atomic: runs in the caller's transaction under the
    attacker's advisory lock (same lock every strike route uses), so two
    concurrent launches can't spend one nuke twice or both skip the cost."""
    db.execute("SELECT pg_advisory_xact_lock(%s)", (attacker_id,))
    plan = plan_strike(db, attacker_id, war_id, province_id)
    if plan["blocked"]:
        raise StrikeError(plan["blocked"])
    target = plan["target"]

    db.execute(
        """
        UPDATE user_military um SET quantity = um.quantity - 1
        FROM unit_dictionary ud
        WHERE ud.unit_id = um.unit_id AND ud.name = 'nukes'
          AND um.user_id = %s AND um.quantity > 0
        RETURNING um.quantity
        """,
        (attacker_id,),
    )
    if not db.fetchone():
        raise StrikeError("You don't have any nukes.")

    # Iron Dome (migration 0104): the struck province's domes get one shot at
    # the warhead. The nuke is spent either way; an intercept does no damage.
    from app_core.military.iron_dome import roll_intercepts

    if roll_intercepts(db, plan["enemy_id"], 1, "nukes", province_id=province_id):
        prov_name = target.get("name", "the province")
        db.execute(
            "INSERT INTO news (destination_id, message) VALUES (%s, %s), (%s, %s)",
            (
                plan["enemy_id"],
                f"🛡️ IRON DOME: {plan['attacker_name']} launched a nuke at your province "
                f"{prov_name}. Your Iron Domes shot it down. No damage was done.",
                attacker_id,
                f"🛡️ Your nuke at {plan['enemy_name']}'s province {prov_name} was "
                f"intercepted by Iron Dome. No damage was done.",
            ),
        )
        return {
            "intercepted": True,
            "attacker_name": plan["attacker_name"],
            "enemy_name": plan["enemy_name"],
            "enemy_id": plan["enemy_id"],
            "province_name": prov_name,
            "deaths": 0, "death_pct": 0.0, "cities_destroyed": 0,
            "buildings_destroyed": 0, "happiness_lost": 0, "multiplier": 1.0,
            "is_retaliation": plan["is_retaliation"], "cost": 0,
            "influence_before": plan["influence"], "recovery_days": RECOVERY_DAYS,
        }

    # Lock the province row and recompute from its current values.
    db.execute(
        """
        SELECT id, provincename, COALESCE(population, 0), COALESCE(land, 0),
               COALESCE(CAST(citycount AS INTEGER), 0), COALESCE(happiness, 0)
        FROM provinces WHERE id = %s AND userid = %s FOR UPDATE
        """,
        (province_id, plan["enemy_id"]),
    )
    row = db.fetchone()
    if not row:
        raise StrikeError("That province doesn't belong to your enemy in this war.")
    prov = {
        "id": row[0],
        "name": row[1],
        "population": int(row[2]),
        "land": int(row[3]),
        "citycount": int(row[4]),
        "happiness": int(row[5]),
    }
    dmg = strike_damage(prov, target["damage"]["multiplier"])
    pop = prov["population"]
    survive = 1.0 - (dmg["deaths"] / pop) if pop > 0 else 1.0

    # Population. The age split (pop_children/working/elderly) is rescaled
    # proportionally by the trg_sync_province_population trigger (migration
    # 0020) when only `population` changes, so it must NOT be set here too
    # (setting it would make the trigger recompute population from it).
    # The education split has no trigger, so it is scaled here.
    db.execute(
        """
        UPDATE provinces SET
            population = GREATEST(0, population - %s),
            edu_none = FLOOR(COALESCE(edu_none, 0) * %s),
            edu_highschool = FLOOR(COALESCE(edu_highschool, 0) * %s),
            edu_college = FLOOR(COALESCE(edu_college, 0) * %s),
            citycount = GREATEST(0, COALESCE(CAST(citycount AS INTEGER), 0) - %s),
            happiness = GREATEST(0, COALESCE(happiness, 0) - %s)
        WHERE id = %s
        """,
        (
            dmg["deaths"],
            survive, survive, survive,
            dmg["cities_destroyed"],
            dmg["happiness_lost"],
            province_id,
        ),
    )

    # Buildings in the province, destroyed proportionally (floor per type).
    db.execute(
        """
        WITH d AS (
            SELECT ctid AS rid, FLOOR(quantity * %s)::int AS lost
            FROM user_buildings
            WHERE user_id = %s AND province_id = %s AND quantity > 0
        ), hit AS (
            UPDATE user_buildings ub SET quantity = ub.quantity - d.lost
            FROM d WHERE ub.ctid = d.rid AND d.lost >= 1
            RETURNING d.lost
        )
        SELECT COALESCE(SUM(lost), 0) FROM hit
        """,
        (dmg["infra_frac"], plan["enemy_id"], province_id),
    )
    buildings_destroyed = int(db.fetchone()[0] or 0)

    # 2026-10-04 rebalance (wars/aftermath.py): radiation kills
    # NUKE_FALLOUT_DEATHS of the target's WHOLE nation (so spreading out over
    # many provinces doesn't make a nation nuke-proof).
    from wars import aftermath as war_aftermath

    fallout_deaths = war_aftermath.kill_civilians(
        db, plan["enemy_id"], war_aftermath.NUKE_FALLOUT_DEATHS
    )

    now = datetime.now(timezone.utc)
    cost = plan["cost"]
    db.execute(
        """
        INSERT INTO nuclear_strikes (
            war_id, attacker_id, target_id, province_id, province_name,
            launched_at, recovers_at, is_retaliation, influence_before,
            influence_cost, damage_multiplier, deaths, cities_destroyed,
            buildings_destroyed, happiness_lost)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            war_id, attacker_id, plan["enemy_id"], province_id, prov["name"],
            now, now + timedelta(days=RECOVERY_DAYS), plan["is_retaliation"],
            plan["influence"], cost, round(dmg["multiplier"], 4), dmg["deaths"],
            dmg["cities_destroyed"], buildings_destroyed, dmg["happiness_lost"],
        ),
    )
    strike_id = db.fetchone()[0]

    result = {
        "strike_id": strike_id,
        "war_id": war_id,
        "attacker_name": plan["attacker_name"],
        "enemy_name": plan["enemy_name"],
        "enemy_id": plan["enemy_id"],
        "province_name": prov["name"],
        "deaths": dmg["deaths"],
        "death_pct": (dmg["deaths"] / pop * 100.0) if pop else 0.0,
        "cities_destroyed": dmg["cities_destroyed"],
        "buildings_destroyed": buildings_destroyed,
        "happiness_lost": dmg["happiness_lost"],
        "multiplier": dmg["multiplier"],
        "is_retaliation": plan["is_retaliation"],
        "cost": cost,
        "influence_before": plan["influence"],
        "recovery_days": RECOVERY_DAYS,
        "fallout_deaths": fallout_deaths,
    }

    kind = "retaliatory nuclear strike" if plan["is_retaliation"] else "nuclear strike"
    target_news = (
        f"☢️ NUCLEAR STRIKE: {plan['attacker_name']} launched a {kind} on your "
        f"province {prov['name']}. {dmg['deaths']:,} people were killed "
        f"({result['death_pct']:.1f}% of the province), {dmg['cities_destroyed']:,} "
        f"cities and {buildings_destroyed:,} buildings were destroyed, and "
        f"happiness there fell by {dmg['happiness_lost']}. Radiation killed "
        f"{fallout_deaths:,} more across your nation."
    )
    attacker_news = (
        f"☢️ Your {kind} hit {plan['enemy_name']}'s province {prov['name']}: "
        f"{dmg['deaths']:,} killed, {dmg['cities_destroyed']:,} cities and "
        f"{buildings_destroyed:,} buildings destroyed, plus {fallout_deaths:,} "
        f"radiation deaths across their nation. The world's reaction costs "
        f"you {cost:,} influence, recovering over {RECOVERY_DAYS} days."
    )
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s), (%s, %s)",
        (plan["enemy_id"], target_news, attacker_id, attacker_news),
    )
    try:
        from app_core.world_affairs.services import log_event

        log_event(
            db,
            "war",
            f"☢️ {plan['attacker_name']} launched a {kind} on "
            f"{plan['enemy_name']}'s province {prov['name']}.",
            actor_id=attacker_id,
            target_id=plan["enemy_id"],
        )
    except Exception:
        pass
    return result
