"""The Golden Throne: daily sacrifice, vitality, pilgrims, Wall of the Spent, events.

Pure functions (math, dawn dates, tiers) are separated from the DB functions so the rules can
be unit-tested without Postgres. All numbers come from golden_throne_config.
"""
import random
from datetime import date, datetime, timedelta, timezone

from app_core.world_affairs.services import log_event

from . import golden_throne_config as C

TRAIT_KEY = "golden_throne"
PILGRIM_MESSAGES = {
    "already": "You have already sent pilgrims for the coming dawn.",
    "self": "The Throne does not need pilgrims from its own hive.",
    "bot": "Machine-spirits cannot make pilgrimage.",
    "young": "Your nation is too young to send pilgrims.",
    "pop": "You do not have enough people to send.",
    "noowner": "The Golden Throne is not active.",
}


# ----------------------------- pure rules -------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc)


def local(now=None):
    return (now or now_utc()).astimezone(C.SERVER_TZ)


def next_dawn_date(now=None):
    """Date of the dawn that the next pilgrimage will be offered at."""
    n = local(now)
    return n.date() if n.time() < C.DAWN_TIME else n.date() + timedelta(days=1)


def next_dawn_at(now=None):
    d = next_dawn_date(now)
    return datetime.combine(d, C.DAWN_TIME, tzinfo=C.SERVER_TZ)


def due_dawn(last_dawn, now=None):
    """The dawn date to process now, or None. Missed days are skipped, never replayed."""
    n = local(now)
    if n.time() < C.DAWN_TIME:
        return None
    today = n.date()
    return today if (last_dawn is None or last_dawn < today) else None


def vigil_day(vigil_start, now=None):
    return max(1, (local(now).date() - vigil_start).days + 1)


def tier_for(vitality, crisis=False):
    """dict(key, label, happiness, defense, food) for a vitality value."""
    if crisis:
        k, label, hap, dfn, food = C.CRISIS_TIER
        return {"key": k, "label": label, "happiness": hap, "defense": dfn, "food": food}
    v = float(vitality)
    for floor, k, label, hap, dfn, food in C.TIERS:
        if v >= floor:
            return {"key": k, "label": label, "happiness": hap, "defense": dfn, "food": food}
    k, label, hap, dfn, food = C.CRISIS_TIER
    return {"key": k, "label": label, "happiness": hap, "defense": dfn, "food": food}


def split_souls(pilgrim_weight):
    """(souls_from_pilgrims, souls_from_own_people): pilgrims offset the sacrifice first."""
    from_pilgrims = max(0, min(int(pilgrim_weight), C.SACRIFICE_SOULS))
    return from_pilgrims, C.SACRIFICE_SOULS - from_pilgrims


def vitality_delta(pilgrim_weight, sacrificed, crisis):
    bonus = C.PILGRIM_RESTORE_EACH * min(max(0, int(pilgrim_weight)), C.PILGRIM_RESTORE_CAP_WEIGHT)
    if not sacrificed:
        return -(C.DEVOUR + C.SKIP_EXTRA_PENALTY)
    if crisis:  # decay paused while the hive rallies
        return C.CRISIS_RECOVERY + bonus
    return -C.DEVOUR + C.SACRIFICE_RESTORE + bonus


def clamp_vitality(v):
    return round(max(0.0, min(100.0, float(v))), 2)


def next_crisis(prev_crisis, vitality_after):
    if prev_crisis:
        return vitality_after < C.CRISIS_EXIT_AT
    return vitality_after <= C.CRISIS_ENTER_AT


def pilgrim_weight_now(state_event, event_ends_at, now=None):
    """Weight one pilgrimage counts for right now (doubled during a Pilgrim Surge)."""
    n = now or now_utc()
    if state_event == "surge" and event_ends_at and event_ends_at > n:
        return C.SURGE_MULTIPLIER
    return 1


def roll_event(rng, last_event_day, today):
    """Returns an event key or None. At most one per EVENT_MIN_GAP_DAYS, ~1/week."""
    if last_event_day and (today - last_event_day).days < C.EVENT_MIN_GAP_DAYS:
        return None
    if rng.random() >= C.EVENT_CHANCE_PER_DAWN:
        return None
    keys = list(C.EVENTS)
    return rng.choices(keys, weights=[C.EVENTS[k]["weight"] for k in keys])[0]


# ----------------------------- DB helpers -------------------------------------------------
def take_population(db, user_id, n):
    """Remove up to n people from the largest provinces (never below 1 per province).
    Returns how many were actually taken."""
    db.execute(
        "SELECT id, population FROM provinces WHERE userid=%s ORDER BY population DESC "
        "FOR UPDATE",
        (user_id,),
    )
    taken = 0
    for pid, pop in db.fetchall():
        if taken >= n:
            break
        take = min(n - taken, max(0, int(pop) - 1))
        if take <= 0:
            continue
        db.execute(
            "UPDATE provinces SET population = population - %s, "
            "pop_working = GREATEST(0, pop_working - %s) WHERE id=%s",
            (take, take, pid),
        )
        taken += take
    return taken


def total_population(db, user_id):
    db.execute("SELECT COALESCE(SUM(population),0) FROM provinces WHERE userid=%s", (user_id,))
    row = db.fetchone()
    return int(row[0]) if row else 0


def owner_id(db):
    """The nation currently holding the Golden Throne trait (None if inactive)."""
    db.execute(
        "SELECT user_id FROM nation_traits WHERE trait_key=%s AND enabled LIMIT 1",
        (TRAIT_KEY,),
    )
    row = db.fetchone()
    return int(row[0]) if row else None


def ensure_state(db, user_id, now=None):
    """Create the throne_state row for a holder (idempotent)."""
    db.execute(
        "INSERT INTO throne_state (user_id, vitality, vigil_start) "
        "SELECT %s, %s, %s WHERE EXISTS (SELECT 1 FROM users WHERE id=%s) "
        "ON CONFLICT (user_id) DO NOTHING",
        (user_id, C.START_VITALITY, local(now).date(), user_id),
    )


# ----------------------------- the dawn tick ----------------------------------------------
def run_dawn(db, user_id, now=None, rng=None):
    """Run today's dawn for one throne holder. Idempotent: returns None if already done/not due.

    Concurrency: the throne_state row is locked, and throne_days.day is a primary key inserted
    with ON CONFLICT DO NOTHING, so two workers or a retry can never run a dawn twice."""
    rng = rng or random
    now = now or now_utc()
    db.execute(
        "SELECT vitality, last_dawn, crisis, active_event, event_ends_at, last_event_day, "
        "souls_total FROM throne_state WHERE user_id=%s FOR UPDATE",
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return None
    vitality, last_dawn, crisis, active_event, event_ends_at, last_event_day, souls_total = row
    day = due_dawn(last_dawn, now)
    if day is None:
        return None
    db.execute(
        "INSERT INTO throne_days (day, vitality_after) VALUES (%s, %s) "
        "ON CONFLICT (day) DO NOTHING RETURNING day",
        (day, float(vitality)),
    )
    if db.fetchone() is None:
        return None

    # Expire a finished event before counting today's pilgrims.
    cur_event, cur_end = active_event, event_ends_at
    if cur_event and cur_end and cur_end <= now:
        cur_event, cur_end = None, None

    db.execute(
        "SELECT COALESCE(SUM(weight),0), COUNT(*) FROM throne_pilgrimages WHERE for_dawn=%s",
        (day,),
    )
    weight, n_pilgrims = (int(x) for x in db.fetchone())
    from_pilgrims, from_own = split_souls(weight)

    skipped = False
    if from_own > 0:
        if total_population(db, user_id) < C.MIN_POPULATION_FOR_SACRIFICE:
            skipped = True
        else:
            take_population(db, user_id, from_own)
    sacrificed = not skipped
    delta = vitality_delta(weight if sacrificed else 0, sacrificed, bool(crisis))
    new_v = clamp_vitality(float(vitality) + delta)
    souls_given = (from_pilgrims + from_own) if sacrificed else 0

    # Rare event roll (never replaces a still-running one).
    event = None
    if not cur_event:
        event = roll_event(rng, last_event_day, day)
    event_text = None
    if event == "whispers":
        choice = rng.choice(C.WHISPERS_CHOICES)
        event_text = choice["text"]
        if choice["kind"] == "vitality":
            new_v = clamp_vitality(new_v + choice["amount"])
        else:
            cur_event = f"whispers:{choice['kind']}"
            cur_end = now + timedelta(hours=C.EVENT_DURATION_HOURS)
    elif event == "heretics":
        new_v = clamp_vitality(new_v - C.HERETIC_VITALITY_LOSS)
        cur_event = "heretics"
        cur_end = now + timedelta(hours=C.EVENT_DURATION_HOURS)
        event_text = "Heretic Uprising: unrest in the lower hive."
    elif event == "surge":
        cur_event = "surge"
        cur_end = now + timedelta(hours=C.EVENT_DURATION_HOURS)
        event_text = "Pilgrim Surge: every pilgrimage counts double."

    new_crisis = next_crisis(bool(crisis), new_v)
    tier = tier_for(new_v, new_crisis)
    db.execute(
        "UPDATE throne_days SET souls_own=%s, souls_pilgrim=%s, pilgrims=%s, vitality_after=%s, "
        "event=%s, skipped=%s WHERE day=%s",
        (from_own if sacrificed else 0, from_pilgrims if sacrificed else 0, n_pilgrims, new_v,
         event_text or (C.EVENTS[event]["label"] if event else None), skipped, day),
    )
    db.execute(
        "UPDATE throne_state SET vitality=%s, last_dawn=%s, crisis=%s, souls_total=%s, "
        "active_event=%s, event_ends_at=%s, last_event_day=%s WHERE user_id=%s",
        (new_v, day, new_crisis, int(souls_total) + souls_given,
         cur_event, cur_end, day if event else last_event_day, user_id),
    )
    msg = C.WARNINGS[tier["key"]]
    log_event(
        db, "golden_throne",
        f"Dawn on Holy Terra: {souls_given} souls given. {tier['label']} ({new_v:g}/100). {msg}",
        actor_id=user_id,
    )
    return {"day": day, "vitality": new_v, "tier": tier["key"], "souls": souls_given,
            "skipped": skipped, "event": event, "crisis": new_crisis, "pilgrims": n_pilgrims}


# ----------------------------- pilgrimage -------------------------------------------------
class NotEnoughPeople(Exception):
    pass


def send_pilgrims(db, user_id, now=None):
    """Returns (ok, message). One pilgrimage per nation per dawn window, atomic.
    The offering is always population: PILGRIM_COST_POPULATION people leave the pilgrim's
    nation and are recorded on the Wall of the Spent.

    The UNIQUE (for_dawn, pilgrim_user_id) row is inserted first, inside a savepoint with the
    cost; if the cost cannot be paid the savepoint rolls the row back, so the limit can't be
    burned without paying and can't be used twice without a second payment."""
    now = now or now_utc()
    owner = owner_id(db)
    if owner is None:
        return False, PILGRIM_MESSAGES["noowner"]
    if int(user_id) == owner:
        return False, PILGRIM_MESSAGES["self"]
    db.execute("SELECT auth_type, date FROM users WHERE id=%s", (user_id,))
    u = db.fetchone()
    if not u:
        return False, PILGRIM_MESSAGES["noowner"]
    if u[0] == "bot":
        return False, PILGRIM_MESSAGES["bot"]
    try:
        created = datetime.strptime(str(u[1])[:10], "%Y-%m-%d").date()
        if (local(now).date() - created).days < C.PILGRIM_MIN_ACCOUNT_AGE_DAYS:
            return False, PILGRIM_MESSAGES["young"]
    except ValueError:
        pass

    db.execute(
        "SELECT active_event, event_ends_at FROM throne_state WHERE user_id=%s", (owner,)
    )
    st = db.fetchone() or (None, None)
    weight = pilgrim_weight_now(st[0], st[1], now)
    dawn = next_dawn_date(now)

    db.execute("SAVEPOINT throne_pilgrimage")
    db.execute(
        "INSERT INTO throne_pilgrimages (for_dawn, pilgrim_user_id, weight, cost_kind) "
        "VALUES (%s, %s, %s, 'population') ON CONFLICT (for_dawn, pilgrim_user_id) DO NOTHING "
        "RETURNING id",
        (dawn, user_id, weight),
    )
    row = db.fetchone()
    if row is None:
        db.execute("ROLLBACK TO SAVEPOINT throne_pilgrimage")
        return False, PILGRIM_MESSAGES["already"]
    try:
        people = take_population(db, user_id, C.PILGRIM_COST_POPULATION)
        if people < C.PILGRIM_COST_POPULATION:
            raise NotEnoughPeople()
    except NotEnoughPeople:
        db.execute("ROLLBACK TO SAVEPOINT throne_pilgrimage")
        return False, PILGRIM_MESSAGES["pop"]
    db.execute("UPDATE throne_pilgrimages SET people=%s WHERE id=%s", (people, row[0]))
    db.execute("RELEASE SAVEPOINT throne_pilgrimage")

    db.execute(
        "INSERT INTO throne_blessings (user_id, expires_at, pct) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET expires_at = EXCLUDED.expires_at, pct = EXCLUDED.pct",
        (user_id, now + timedelta(hours=C.PILGRIM_BLESSING_HOURS), C.PILGRIM_BLESSING_PCT),
    )
    log_event(db, "golden_throne_pilgrim", "Pilgrims were sent to the Golden Throne.",
              actor_id=user_id, target_id=owner)
    return True, (
        f"Your pilgrims reach Holy Terra. The Throne blesses your people "
        f"(+{C.PILGRIM_BLESSING_PCT:g}% happiness for {C.PILGRIM_BLESSING_HOURS}h)."
    )


# ----------------------------- modifiers + page -------------------------------------------
def holder_modifiers(state, now=None):
    """Modifier dict for a holder row: (vitality, crisis, active_event, event_ends_at)."""
    vitality, crisis, event, ends = state
    now = now or now_utc()
    tier = tier_for(vitality, crisis)
    hap = tier["happiness"]
    industry = C.HIVE_INDUSTRY_MULT
    if event and ends and ends > now:
        if event == "heretics":
            hap += C.HERETIC_HAPPINESS_PCT
        elif event == "whispers:happiness":
            hap += 2.0
        elif event == "whispers:industry":
            industry *= 1.05
    return {
        "happiness_pct": hap,
        "industry_mult": industry,
        "food_mult": C.HIVE_FOOD_MULT * (1 + tier["food"] / 100.0),
        "upkeep_mult": C.HIVE_UPKEEP_MULT,
        "pop_cap_mult": C.HIVE_POP_CAP_MULT,
        "defense_pct": tier["defense"],
    }


def wall_page(db, before=None, limit=None):
    """Public Wall of the Spent: newest dawn first. Returns (rows, next_before)."""
    limit = limit or C.WALL_PAGE_SIZE
    if before:
        db.execute(
            "SELECT day, souls_own, souls_pilgrim, pilgrims, event, skipped FROM throne_days "
            "WHERE day < %s ORDER BY day DESC LIMIT %s", (before, limit + 1))
    else:
        db.execute(
            "SELECT day, souls_own, souls_pilgrim, pilgrims, event, skipped FROM throne_days "
            "ORDER BY day DESC LIMIT %s", (limit + 1,))
    rows = db.fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    names = {}
    if rows:
        db.execute(
            "SELECT p.for_dawn, u.id, u.username, p.people FROM throne_pilgrimages p "
            "JOIN users u ON u.id = p.pilgrim_user_id WHERE p.for_dawn = ANY(%s) "
            "ORDER BY p.id", ([r[0] for r in rows],))
        for d, uid, name, people in db.fetchall():
            names.setdefault(d, []).append({"id": uid, "name": name, "people": int(people or 0)})
    out = [
        {"day": r[0].isoformat(), "souls_own": r[1], "souls_pilgrim": r[2], "pilgrims": r[3],
         "event": r[4], "skipped": r[5], "nations": names.get(r[0], [])}
        for r in rows
    ]
    return out, (out[-1]["day"] if more and out else None)


def card(db, now=None):
    """Tiny summary for the pinned 'Holy Terra' card on the /countries directory."""
    owner = owner_id(db)
    if owner is None:
        return None
    db.execute("SELECT vitality, crisis, vigil_start FROM throne_state WHERE user_id=%s", (owner,))
    row = db.fetchone()
    if not row:
        return None
    return {"owner_id": owner, "tier_label": tier_for(row[0], row[1])["label"],
            "vigil_day": vigil_day(row[2], now)}


def page_context(db, owner, viewer_id, now=None):
    """Everything the nation-page partial needs. None if the Throne isn't active."""
    now = now or now_utc()
    db.execute(
        "SELECT vitality, crisis, active_event, event_ends_at, vigil_start, souls_total "
        "FROM throne_state WHERE user_id=%s", (owner,))
    row = db.fetchone()
    if not row:
        return None
    vitality, crisis, event, ends, start, souls_total = row
    tier = tier_for(vitality, crisis)
    dawn = next_dawn_date(now)
    db.execute("SELECT COUNT(*), COALESCE(SUM(weight),0) FROM throne_pilgrimages WHERE for_dawn=%s",
               (dawn,))
    waiting, waiting_weight = (int(x) for x in db.fetchone())
    sent = False
    blessing = None
    if viewer_id:
        db.execute("SELECT 1 FROM throne_pilgrimages WHERE for_dawn=%s AND pilgrim_user_id=%s",
                   (dawn, viewer_id))
        sent = db.fetchone() is not None
        db.execute("SELECT expires_at, pct FROM throne_blessings WHERE user_id=%s AND expires_at>%s",
                   (viewer_id, now))
        b = db.fetchone()
        blessing = {"expires_at": b[0], "pct": float(b[1])} if b else None
    rows, nxt = wall_page(db)
    event_label = None
    if event and ends and ends > now:
        event_label = {"surge": "Pilgrim Surge", "heretics": "Heretic Uprising"}.get(
            event, "Whispers from the Throne")
    return {
        "vitality": float(vitality), "tier": tier, "crisis": bool(crisis),
        "warning": C.WARNINGS[tier["key"]], "vigil_day": vigil_day(start, now),
        "next_dawn_iso": next_dawn_at(now).astimezone(timezone.utc).isoformat(),
        "souls_total": int(souls_total), "waiting": waiting, "waiting_weight": waiting_weight,
        "event_label": event_label, "viewer_id": viewer_id, "is_owner": viewer_id == owner,
        "sent": sent, "blessing": blessing, "wall": rows, "wall_next": nxt,
        "cost_pop": C.PILGRIM_COST_POPULATION,
        "blessing_pct": C.PILGRIM_BLESSING_PCT, "blessing_hours": C.PILGRIM_BLESSING_HOURS,
        "defense_pct": tier["defense"],
    }
