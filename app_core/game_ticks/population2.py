"""Population 2.0 (community vote 2026-10-06..09, 9 yes / 1 no / 3 change).

Pure functions only: every rate below is per GAME DAY (1 game day = 24 hourly
ticks), the tick passes dt = 1/24. Province demographics are driven by homes
(districts, land, transit), births, hospital-dependent deaths, internal
migration and settlers, instead of the old nation-wide "comfort" growth curve.

Changes made after reading the vote thread (announced with the go-live post):
 * settlers 10%/day of empty homes (was 20%; "mathematically a bit too fast")
 * no education penalty on births ("educated people have fewer kids" was
   disputed; the real brake is housing/food/happiness/healthcare)
 * emigration abroad after the grace period: 2%/day of the people above 120%
"""
import datetime
import math

import variables

POP2_START = datetime.datetime(2026, 10, 12, 18, 0, 0, tzinfo=datetime.timezone.utc)
GRACE_DAYS = 14

BASE_HOMES = 2_000_000
HOMES_PER_DISTRICT = 50_000
HOMES_PER_LAND = 30_000
TRANSIT_BONUS = {"railways": 0.01, "metros": 0.02, "monorails": 0.03}
TRANSIT_MAX = 0.30

CHILD_DAYS = 18  # child -> working
WORKING_DAYS = 27  # working (18) -> elderly (45)

BIRTH_RATE = 0.025
ELDERLY_DEATH = (0.06, 0.02)  # uncovered, fully covered by hospitals
CHILD_DEATH = (0.01, 0.002)
HEALTHCARE_POLICY_MULT = 0.7
POLLUTION_DEATH_MULT = 0.25
HOSPITAL_CAPACITY = 1_000_000
MEGACITY_POP = 200_000_000

MIGRATION_RATE = 0.05
SETTLER_RATE = 0.10
SETTLER_CAP_BASE = 500_000
SETTLER_CAP_SHARE = 0.001
OVERFLOW_LIMIT = 1.20
EMIGRATION_RATE = 0.02
SETTLER_WORKING_SHARE = 0.7

DT = 1 / 24


def pop2_active(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now >= POP2_START


def in_grace_period(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now < POP2_START + datetime.timedelta(days=GRACE_DAYS)


def homes(districts, land, buildings):
    transit = sum(
        TRANSIT_BONUS[k] * int(buildings.get(k, 0) or 0) for k in TRANSIT_BONUS
    )
    transit = min(TRANSIT_MAX, transit)
    base = BASE_HOMES + HOMES_PER_DISTRICT * (districts or 0) + HOMES_PER_LAND * (land or 0)
    return int(base * (1 + transit))


def housing_factor(pop, home_count):
    """1 up to 100% full, linear to 0 at 120%."""
    if home_count <= 0:
        return 0.0
    r = pop / home_count
    if r <= 1:
        return 1.0
    return max(0.0, 1 - (r - 1) / (OVERFLOW_LIMIT - 1))


def happiness_factor(happiness):
    return 0.5 + max(0.0, min(100.0, float(happiness or 0))) / 100


def hospital_cover(hospitals, pop):
    if pop <= 0:
        return 1.0
    strength = hospitals * HOSPITAL_CAPACITY
    if pop > MEGACITY_POP:
        strength *= math.sqrt(MEGACITY_POP / pop)
    return min(1.0, strength / pop)


def death_rates(hospitals, pop, pollution, universal_healthcare):
    cover = hospital_cover(hospitals, pop)
    mult = 1 + POLLUTION_DEATH_MULT * max(0.0, float(pollution or 0)) / 100
    if universal_healthcare:
        mult *= HEALTHCARE_POLICY_MULT
    elderly = (ELDERLY_DEATH[0] - (ELDERLY_DEATH[0] - ELDERLY_DEATH[1]) * cover) * mult
    child = (CHILD_DEATH[0] - (CHILD_DEATH[0] - CHILD_DEATH[1]) * cover) * mult
    return elderly, child


def births(working, pop, home_count, happiness, food_ratio, dt=DT):
    food = max(0.0, min(1.0, float(food_ratio or 0)))
    return int(
        working * BIRTH_RATE * housing_factor(pop, home_count)
        * happiness_factor(happiness) * food * dt
    )


def settlers(pop, home_count, happiness, food_ratio, dt=DT):
    free = max(0, home_count - pop)
    cap = SETTLER_CAP_BASE + SETTLER_CAP_SHARE * pop
    food = max(0.0, min(1.0, float(food_ratio or 0)))
    daily = min(SETTLER_RATE * free, cap) * happiness_factor(happiness) * food
    return int(daily * dt)


def emigrants(pop, home_count, dt=DT):
    over = pop - OVERFLOW_LIMIT * home_count
    return int(max(0, over) * EMIGRATION_RATE * dt)


def step_province(p, hospitals, home_count, food_ratio, universal_healthcare, grace, dt=DT):
    """One tick for one province. p has pop_children/working/elderly,
    happiness, pollution. Returns (children, working, elderly) deltas from
    births, deaths and settlers/emigration (NOT aging, NOT migration)."""
    c, w, e = p["pop_children"], p["pop_working"], p["pop_elderly"]
    pop = c + w + e
    er, cr = death_rates(hospitals, pop, p.get("pollution"), universal_healthcare)
    d_e = int(e * er * dt)
    d_c = int(c * cr * dt)
    b = births(w, pop, home_count, p.get("happiness"), food_ratio, dt)
    s = settlers(pop, home_count, p.get("happiness"), food_ratio, dt)
    s_w = int(s * SETTLER_WORKING_SHARE)
    out = 0 if grace else emigrants(pop, home_count, dt)
    out_w = min(w, out)
    return b + (s - s_w) - d_c, s_w - out_w, -d_e


def distribute_migration(provinces, dt=DT):
    """Internal migration inside ONE nation. provinces: list of dicts with
    id, pop, homes. Returns {id: net_change}. Overflow (above 100%) moves
    MIGRATION_RATE/day to provinces with free homes, in proportion to free."""
    out = {p["id"]: 0 for p in provinces}
    free = {p["id"]: max(0, p["homes"] - p["pop"]) for p in provinces}
    total_free = sum(free.values())
    if total_free <= 0:
        return out
    for p in provinces:
        over = p["pop"] - p["homes"]
        if over <= 0:
            continue
        moving = min(int(over * MIGRATION_RATE * dt), total_free)
        if moving <= 0:
            continue
        out[p["id"]] -= moving
        for q in provinces:
            if free[q["id"]]:
                out[q["id"]] += int(moving * free[q["id"]] / total_free)
    return out


# ---------------------------------------------------------------------------
# Nation-level step, shared by the hourly tick and the nation-page projection
# ---------------------------------------------------------------------------
STARVATION_PER_TICK = 0.01  # unchanged: up to 1%/tick at 0 rations coverage


def fetch_province_buildings(cur, province_ids):
    """{province_id: {building_name: qty}} for hospitals + transit only."""
    names = ["hospitals", *TRANSIT_BONUS]
    out = {}
    if not province_ids:
        return out
    cur.execute(
        """
        SELECT ub.province_id, bd.name, COALESCE(SUM(ub.quantity), 0)
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.province_id = ANY(%s) AND bd.name = ANY(%s)
        GROUP BY ub.province_id, bd.name
        """,
        (list(province_ids), names),
    )
    for pid, name, qty in cur.fetchall():
        out.setdefault(pid, {})[name] = int(qty or 0)
    return out


def fetch_healthcare_users(cur, user_ids):
    """Set of user ids with the Universal Healthcare policy."""
    if not user_ids:
        return set()
    cur.execute(
        "SELECT user_id, education FROM policies WHERE user_id = ANY(%s)",
        (list(user_ids),),
    )
    return {
        uid
        for uid, pol in cur.fetchall()
        if pol and variables.POLICY_UNIVERSAL_HEALTHCARE in pol
    }


def _norm(prov):
    c = int(prov.get("pop_children") or 0)
    w = int(prov.get("pop_working") or 0)
    e = int(prov.get("pop_elderly") or 0)
    total = int(prov.get("population") or 0)
    if c + w + e == 0 and total > 0:
        c = total
    return c, w, e


def _scale_down(c, w, e, remove):
    total = c + w + e
    if total <= 0 or remove <= 0:
        return c, w, e
    remove = min(remove, total)
    rc = int(round(remove * c / total))
    re_ = int(round(remove * e / total))
    rw = remove - rc - re_
    return max(0, c - rc), max(0, w - rw), max(0, e - re_)


def simulate_nation(provs, buildings_map, food_ratio, healthcare, starve_grace, now=None):
    """provs: dicts with id, population, pop_children/working/elderly,
    citycount, land, happiness, pollution (one nation). Returns
    {province_id: (children, working, elderly)} after one tick of births,
    deaths, starvation, settlers, emigration and internal migration."""
    grace = in_grace_period(now)
    state = {}
    for p in provs:
        b = buildings_map.get(p["id"], {})
        home_count = homes(p.get("citycount"), p.get("land"), b)
        c, w, e = _norm(p)
        dc, dw, de = step_province(
            {"pop_children": c, "pop_working": w, "pop_elderly": e,
             "happiness": p.get("happiness"), "pollution": p.get("pollution")},
            int(b.get("hospitals", 0) or 0), home_count, food_ratio, healthcare, grace,
        )
        c, w, e = max(0, c + dc), max(0, w + dw), max(0, e + de)
        if not starve_grace and food_ratio < 1.0:
            sd = int((c + w + e) * (1.0 - max(0.0, food_ratio)) * STARVATION_PER_TICK)
            c, w, e = _scale_down(c, w, e, sd)
        state[p["id"]] = [c, w, e, home_count]

    mig = distribute_migration(
        [{"id": k, "pop": v[0] + v[1] + v[2], "homes": v[3]} for k, v in state.items()]
    )
    for pid, net in mig.items():
        c, w, e, h = state[pid]
        if net < 0:
            c, w, e = _scale_down(c, w, e, -net)
        elif net > 0:
            nc = int(net * (1 - SETTLER_WORKING_SHARE))
            c, w = c + nc, w + (net - nc)
        state[pid] = [c, w, e, h]
    return {pid: (v[0], v[1], v[2]) for pid, v in state.items()}
