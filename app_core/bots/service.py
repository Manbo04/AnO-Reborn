"""DB side of bot nations: schema, spawning/coverage, hourly upkeep, pruning.

Runs from the leader-only Celery tasks in ``tasks.py``. Everything here uses
a raw psycopg2 connection/cursor from ``get_db_connection()`` and commits
explicitly; helpers never swallow errors silently (callers log them).
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import Dict, List, Optional

from app_core.bots import BOT_AUTH_TYPE
from app_core.bots import profiles

logger = logging.getLogger(__name__)

# Hard cap on bots created in one run, so a first run on a big player base
# can't hold the leader lock for minutes.
MAX_SPAWN_PER_RUN = 40
# Range is by strength, not province count, so bots needn't mirror huge nations
# (each province costs a hex on the world map and a row in every tick).
MAX_BOT_PROVINCES = 8
PRUNE_AFTER_DAYS = 14
ACTIVE_PLAYER_DAYS = 30
CONTINENTS = ("Grassland", "Forest", "Desert", "Tundra")


def ensure_schema(cur) -> None:
    """Idempotent. Creating tables (not altering ``users``) keeps this lock-free."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_nations (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            archetype TEXT NOT NULL,
            tier TEXT NOT NULL,
            provinces INTEGER NOT NULL,
            population_per_province INTEGER NOT NULL,
            army_share DOUBLE PRECISION NOT NULL,
            target_strength BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_in_range_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_war_state (
            war_id INTEGER PRIMARY KEY,
            last_attack_at DOUBLE PRECISION NOT NULL DEFAULT 0,
            attacks INTEGER NOT NULL DEFAULT 0,
            bot_guard_ts DOUBLE PRECISION NOT NULL DEFAULT 0,
            human_action_ts DOUBLE PRECISION NOT NULL DEFAULT 0
        )
        """)


# --------------------------------------------------------------------------
# Reading the world
# --------------------------------------------------------------------------


def fetch_humans(cur) -> List[Dict]:
    """Recently active human nations with their war strength.

    Strength is the game's own (wars/war_range.py): population/1000 plus
    weighted units, so a bot built to a human's number is in that human's
    declarable range by construction.
    """
    from wars.war_range import unit_weight_case_sql

    def query(active_filter: str) -> list:
        cur.execute(
            f"""
            WITH src AS (
                SELECT u.id FROM users u
                WHERE u.auth_type IS DISTINCT FROM %s
                  AND EXISTS (SELECT 1 FROM provinces p WHERE p.userid = u.id)
                  {active_filter}
            )
            SELECT src.id, pc.cnt, pc.pop, COALESCE(m.strength, 0)
            FROM src
            JOIN (
                SELECT userid, COUNT(*) AS cnt, COALESCE(SUM(population), 0) AS pop
                FROM provinces WHERE userid IN (SELECT id FROM src) GROUP BY userid
            ) pc ON pc.userid = src.id
            LEFT JOIN (
                SELECT um.user_id,
                       SUM(um.quantity * {unit_weight_case_sql("LOWER(ud.name)")}) AS strength
                FROM user_military um
                JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
                WHERE um.user_id IN (SELECT id FROM src)
                GROUP BY um.user_id
            ) m ON m.user_id = src.id
            """,
            (BOT_AUTH_TYPE,),
        )
        return cur.fetchall()

    rows = query(
        "AND EXISTS (SELECT 1 FROM login_events le WHERE le.user_id = u.id "
        f"AND le.created_at > now() - interval '{ACTIVE_PLAYER_DAYS} days')"
    )
    if not rows:  # login_events empty/unavailable: fall back to every human
        rows = query("")
    out = []
    for uid, cnt, pop, army in rows:
        pop, army = float(pop or 0), float(army or 0)
        strength = pop / 1000.0 + army
        out.append(
            {
                "id": uid,
                "provinces": int(cnt),
                "strength": strength,
                "army_share": profiles.army_share_of(strength, army),
            }
        )
    return out


def fetch_bots(cur) -> List[Dict]:
    """Bots with their *target* strength.

    The live number dips whenever a bot loses a battle; coverage must not read
    that as "out of range" and spawn replacements for a bot that is about to
    regenerate, so it works from the stored target instead.
    """
    cur.execute("SELECT user_id, provinces, target_strength FROM bot_nations")
    return [
        {"id": r[0], "provinces": int(r[1]), "strength": float(r[2] or 0)}
        for r in cur.fetchall()
    ]


def bot_ids(cur) -> set:
    cur.execute("SELECT user_id FROM bot_nations")
    return {r[0] for r in cur.fetchall()}


# --------------------------------------------------------------------------
# Applying a target state to a nation
# --------------------------------------------------------------------------


def _current_balances(cur, user_id: int):
    cur.execute("SELECT COALESCE(gold, 0) FROM stats WHERE id = %s", (user_id,))
    row = cur.fetchone()
    gold = int(row[0]) if row else 0
    cur.execute(
        "SELECT rd.name, ue.quantity FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id WHERE ue.user_id = %s",
        (user_id,),
    )
    return gold, {n: int(q or 0) for n, q in cur.fetchall()}


def _set_balances(
    cur, user_id: int, gold: int, stock: Dict[str, int], current=None
) -> None:
    """Move gold/stock to the targets as ledger credits and takes (never raw sets)."""
    from app_core.economy import ledger

    cur_gold, cur_stock = current or _current_balances(cur, user_id)
    delta = int(gold) - cur_gold
    if delta > 0:
        ledger.credit_gold(cur, user_id, delta)
    elif delta < 0:
        ledger.take_gold(cur, user_id, -delta)
    ledger.adjust_resources(
        cur, user_id, {r: int(q) - cur_stock.get(r, 0) for r, q in stock.items()}
    )


def _write_units(cur, user_id: int, units: Dict[str, int]) -> None:
    if not units:
        return
    names, qty = zip(*units.items())
    cur.execute(
        """
        INSERT INTO user_military (user_id, unit_id, quantity)
        SELECT %s, ud.unit_id, v.q
        FROM unit_dictionary ud, unnest(%s::text[], %s::bigint[]) AS v(name, q)
        WHERE LOWER(ud.name) = v.name
        ON CONFLICT (user_id, unit_id) DO UPDATE SET quantity = EXCLUDED.quantity
        """,
        (user_id, list(names), [max(0, int(q)) for q in qty]),
    )


def _write_population(
    cur, user_id: int, per_province: int, only_if_below: bool
) -> None:
    working, children, elderly = (
        int(per_province * 0.6),
        int(per_province * 0.3),
        int(per_province * 0.1),
    )
    guard = " AND population < %s" if only_if_below else ""
    params = [children, working, elderly, user_id]
    if only_if_below:
        params.append(int(per_province * 0.95))
    cur.execute(
        "UPDATE provinces SET pop_children = %s, pop_working = %s, pop_elderly = %s "
        "WHERE userid = %s" + guard,
        params,
    )


def _resource_names() -> List[str]:
    from attack_scripts.Nations import Economy

    return list(Economy.resources)


def _size_from_row(row: dict) -> dict:
    return profiles.size_bot(
        provinces=row["provinces"],
        target_strength=row["target_strength"],
        army_share=row["army_share"],
        archetype=row["archetype"],
        tier=row["tier"],
        resource_names=_resource_names(),
    )


# --------------------------------------------------------------------------
# Spawning
# --------------------------------------------------------------------------


def _next_name(cur) -> str:
    cur.execute(
        "SELECT username FROM users WHERE username LIKE %s",
        (f"%{profiles.BOT_SUFFIX}",),
    )
    taken = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM bot_nations")
    index = cur.fetchone()[0]
    return profiles.pick_name(index, taken)


def create_bot(
    conn, cur, *, human: dict, tier: str, archetype: Optional[str] = None
) -> int:
    """Create one fully-provisioned bot sized for ``human``. Returns the new user id."""
    import bcrypt

    from signup import init_user_game_data
    from province import create_province_record

    archetype = archetype or profiles.pick_archetype()
    ratio = profiles.TIERS[tier]["ratio"]
    provinces = min(MAX_BOT_PROVINCES, max(1, int(human["provinces"])))
    size = profiles.size_bot(
        provinces=provinces,
        target_strength=human["strength"] * ratio,
        army_share=human["army_share"],
        archetype=archetype,
        tier=tier,
        resource_names=_resource_names(),
    )
    pop_pp = size["population_per_province"]

    name = _next_name(cur)
    unusable_hash = bcrypt.hashpw(
        secrets.token_hex(32).encode(), bcrypt.gensalt(4)
    ).decode()
    cur.execute(
        "INSERT INTO users (username, email, hash, date, auth_type, is_verified) "
        "VALUES (%s, %s, %s, CURRENT_DATE::text, %s, TRUE) RETURNING id",
        (
            name,
            f"bot-{uuid.uuid4().hex[:12]}@bots.invalid",
            unusable_hash,
            BOT_AUTH_TYPE,
        ),
    )
    user_id = cur.fetchone()[0]

    # Stats, policies, economy/military rows and the first province.
    init_user_game_data(cur, user_id, secrets.choice(CONTINENTS))
    short = name.replace(profiles.BOT_SUFFIX, "")
    for n in range(2, provinces + 1):
        create_province_record(cur, user_id, f"{short} Province {n}"[:40])

    _write_population(cur, user_id, pop_pp, only_if_below=False)
    _set_balances(cur, user_id, size["gold"], size["stock"])
    _write_units(cur, user_id, size["units"])
    cur.execute(
        "INSERT INTO bot_nations (user_id, archetype, tier, provinces, "
        "population_per_province, army_share, target_strength) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            user_id,
            archetype,
            tier,
            provinces,
            pop_pp,
            human["army_share"],
            size["target_strength"],
        ),
    )
    conn.commit()
    logger.info(
        "bots: created %s (id=%s) %s/%s provinces=%s strength~%s",
        name,
        user_id,
        archetype,
        tier,
        provinces,
        size["target_strength"],
    )
    return user_id


def ensure_coverage(conn, cur) -> Dict[str, int]:
    """Give every active human BOTS_PER_PLAYER bots inside their war range."""
    humans = fetch_humans(cur)
    bots = fetch_bots(cur)
    budget = min(profiles.MAX_BOTS - len(bots), MAX_SPAWN_PER_RUN)
    created = 0
    in_range_ids = set()

    # Least-covered first, biggest first on ties: large nations have few
    # neighbours to share bots with and must not starve behind the cap.
    def _coverage(h):
        return sum(
            1 for b in bots if profiles.in_war_range(h["strength"], b["strength"])
        )

    for human in sorted(humans, key=lambda h: (_coverage(h), -h["strength"])):
        covering = [
            b for b in bots if profiles.in_war_range(human["strength"], b["strength"])
        ]
        in_range_ids.update(b["id"] for b in covering)
        if len(covering) >= profiles.BOTS_PER_PLAYER or budget <= 0:
            continue
        for tier in profiles.missing_tiers(
            [(b["strength"], human["strength"]) for b in covering]
        ):
            if budget <= 0:
                break
            try:
                new_id = create_bot(conn, cur, human=human, tier=tier)
            except Exception:
                conn.rollback()
                logger.exception("bots: spawn failed for human %s", human["id"])
                budget = 0
                break
            budget -= 1
            created += 1
            target = human["strength"] * profiles.TIERS[tier]["ratio"]
            bots.append(
                {"id": new_id, "provinces": human["provinces"], "strength": target}
            )
            in_range_ids.add(new_id)

    if in_range_ids:
        cur.execute(
            "UPDATE bot_nations SET last_in_range_at = now() WHERE user_id = ANY(%s)",
            (list(in_range_ids),),
        )
    conn.commit()
    return {"humans": len(humans), "bots": len(bots), "created": created}


# --------------------------------------------------------------------------
# Hourly upkeep
# --------------------------------------------------------------------------


# A bot that is in a war, or whose last war ended less than this long ago, does
# not refill its gold and stockpiles (armies and population still do, so it
# stays a credible opponent). Without this a bot's hourly refill turned every
# raid into a renewable gold/resource faucet.
LOOT_RECOVERY_SECONDS = 72 * 3600


def _bots_in_or_near_war(cur, ids, now=None) -> set:
    now = time.time() if now is None else now
    cur.execute(
        "SELECT DISTINCT u FROM ("
        " SELECT attacker AS u FROM wars WHERE attacker = ANY(%s)"
        "  AND (peace_date IS NULL OR peace_date > %s)"
        " UNION ALL"
        " SELECT defender AS u FROM wars WHERE defender = ANY(%s)"
        "  AND (peace_date IS NULL OR peace_date > %s)"
        ") t",
        (list(ids), now - LOOT_RECOVERY_SECONDS, list(ids), now - LOOT_RECOVERY_SECONDS),
    )
    return {r[0] for r in cur.fetchall()}


def maintain_bots(conn, cur) -> int:
    """Refill every bot toward its target (gradually) and clamp runaway growth."""
    cur.execute(
        "SELECT user_id, archetype, tier, provinces, population_per_province, "
        "army_share, target_strength FROM bot_nations"
    )
    cols = (
        "user_id",
        "archetype",
        "tier",
        "provinces",
        "population_per_province",
        "army_share",
        "target_strength",
    )
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if not rows:
        return 0
    ids = [r["user_id"] for r in rows]

    cur.execute("SELECT id, gold FROM stats WHERE id = ANY(%s)", (ids,))
    gold = {r[0]: r[1] or 0 for r in cur.fetchall()}
    cur.execute(
        "SELECT ue.user_id, rd.name, ue.quantity FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = ANY(%s)",
        (ids,),
    )
    stock: Dict[int, Dict[str, float]] = {}
    for uid, name, qty in cur.fetchall():
        stock.setdefault(uid, {})[name] = float(qty or 0)
    cur.execute(
        "SELECT um.user_id, LOWER(ud.name), um.quantity FROM user_military um "
        "JOIN unit_dictionary ud ON ud.unit_id = um.unit_id WHERE um.user_id = ANY(%s)",
        (ids,),
    )
    units: Dict[int, Dict[str, float]] = {}
    for uid, name, qty in cur.fetchall():
        units.setdefault(uid, {})[name] = float(qty or 0)

    recently_at_war = _bots_in_or_near_war(cur, ids)

    maintained = 0
    for row in rows:
        uid = row["user_id"]
        try:
            target = _size_from_row(row)
            cap = lambda cur_v, tgt: min(cur_v, tgt * 1.5)  # noqa: E731
            frozen = uid in recently_at_war

            g_now = float(gold.get(uid, 0))
            if g_now < target["gold"]:
                new_gold = int(g_now) if frozen else profiles.regen_toward(g_now, target["gold"])
            else:
                new_gold = int(cap(g_now, target["gold"]))

            new_stock = {}
            for res, tgt in target["stock"].items():
                now = stock.get(uid, {}).get(res, 0.0)
                if now < tgt:
                    grown = int(now) if frozen else profiles.regen_toward(now, tgt)
                else:
                    grown = int(cap(now, tgt))
                new_stock[res] = max(grown, int(profiles.upkeep_floor(res, tgt)))
            _set_balances(
                cur,
                uid,
                new_gold,
                new_stock,
                (
                    int(gold.get(uid, 0)),
                    {k: int(v) for k, v in stock.get(uid, {}).items()},
                ),
            )

            new_units = {}
            for unit, tgt in target["units"].items():
                now = units.get(uid, {}).get(unit, 0.0)
                new_units[unit] = (
                    profiles.regen_toward(now, tgt) if now < tgt else int(cap(now, tgt))
                )
            _write_units(cur, uid, new_units)

            _write_population(
                cur, uid, target["population_per_province"], only_if_below=True
            )
            conn.commit()
            maintained += 1
        except Exception:
            conn.rollback()
            logger.exception("bots: maintenance failed for bot %s", uid)
    return maintained


def prune_unused(conn, cur) -> int:
    """Delete bots no active player has had in range for PRUNE_AFTER_DAYS (and not at war)."""
    cur.execute(
        """
        SELECT bn.user_id FROM bot_nations bn
        WHERE bn.last_in_range_at < now() - make_interval(days => %s)
          AND NOT EXISTS (
              SELECT 1 FROM wars w
              WHERE w.peace_date IS NULL AND bn.user_id IN (w.attacker, w.defender)
          )
        """,
        (PRUNE_AFTER_DAYS,),
    )
    removed = 0
    for (uid,) in cur.fetchall():
        try:
            cur.execute("SAVEPOINT bot_prune")
            cur.execute(
                "DELETE FROM users WHERE id = %s AND auth_type = %s",
                (uid, BOT_AUTH_TYPE),
            )
            cur.execute("RELEASE SAVEPOINT bot_prune")
            removed += 1
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT bot_prune")
            logger.warning("bots: could not prune bot %s (still referenced)", uid)
    conn.commit()
    return removed


def run_hourly(conn) -> Dict[str, int]:
    """Coverage -> upkeep -> prune, in that order."""
    cur = conn.cursor()
    ensure_schema(cur)
    conn.commit()
    out = ensure_coverage(conn, cur)
    out["maintained"] = maintain_bots(conn, cur)
    out["pruned"] = prune_unused(conn, cur)
    return out
