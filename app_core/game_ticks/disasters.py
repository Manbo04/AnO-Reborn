"""Hourly tick: each nation has a small chance of a biome-appropriate natural
disaster damaging one resource stockpile, logged as a real /treaties-style
news event.

The game's random news-ticker flavor text (flavor_text*.py) has narrated
disaster relief convoys and evacuations since launch, but nothing backed it
mechanically. This gives that flavor a real, bounded effect instead of
leaving it purely cosmetic.

Standalone tick with its own advisory lock and task_runs row, same pattern
as app_core/game_ticks/unit_production.py -- keeps this rare, self-contained
side effect out of the shared revenue-tick code path.
"""
import random as rand

from app_core.game_ticks.common import should_skip_task, handle_exception, log_verbose
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock

TASK_NAME = "natural_disasters"
ADVISORY_LOCK_ID = 9012

# Chance any single nation is struck in one hourly run. Deliberately rare --
# this is meant to read as world texture, not a punishing mechanic. At ~0.1%
# per nation per hour, an individual nation sees one roughly every 40 days.
DISASTER_CHANCE_PER_NATION = 0.001

# Fraction of the affected resource's stockpile lost, capped in absolute kg
# so a resource-hoarding nation can't lose an implausible amount in one hit.
DAMAGE_FRACTION = 0.10
DAMAGE_CAP_KG = 500_000

# biome (lowercase, matches stats.location) -> (label, resource, message template)
BIOME_DISASTERS = {
    "tundra": (
        "Blizzard",
        "iron",
        "A severe blizzard buried mining operations, destroying {amt} kg of iron reserves.",
    ),
    "desert": (
        "Sandstorm",
        "oil",
        "A violent sandstorm damaged extraction equipment, destroying {amt} kg of raw oil.",
    ),
    "boreal forest": (
        "Wildfire",
        "lumber",
        "A wildfire swept through your boreal forests, destroying {amt} kg of lumber.",
    ),
    "grassland": (
        "Flash Flood",
        "rations",
        "Flash floods swept through your grassland farms, ruining {amt} kg of rations.",
    ),
    "savanna": (
        "Drought",
        "rations",
        "A prolonged drought withered crops across the savanna, destroying {amt} kg of rations.",
    ),
    "mountain range": (
        "Rockslide",
        "coal",
        "A rockslide buried mining infrastructure, destroying {amt} kg of coal reserves.",
    ),
    "jungle": (
        "Monsoon Flooding",
        "lumber",
        "Monsoon flooding disrupted logging operations, destroying {amt} kg of lumber.",
    ),
}


def roll_struck_nations(nations, rng=rand):
    """Pure helper (no DB) -- which (user_id, biome) pairs get struck this
    run, given [(user_id, biome_lowercase), ...]. Split out from
    run_natural_disasters for deterministic testing."""
    return [
        (user_id, biome)
        for user_id, biome in nations
        if biome in BIOME_DISASTERS and rng.random() < DISASTER_CHANCE_PER_NATION
    ]


def compute_disaster_loss(current_quantity):
    """Pure helper -- kg lost given a current stockpile. 0 if nothing to lose."""
    if current_quantity <= 0:
        return 0
    return min(int(current_quantity * DAMAGE_FRACTION), DAMAGE_CAP_KG)


def run_natural_disasters():
    from database import get_db_connection

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return

        try:
            db = conn.cursor()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                (TASK_NAME,),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                (TASK_NAME,),
            )
            row = db.fetchone()
            if should_skip_task(row, TASK_NAME):
                return

            db.execute(
                "SELECT id, LOWER(location) FROM stats WHERE location IS NOT NULL"
            )
            nations = [(uid, loc) for uid, loc in db.fetchall()]

            struck = roll_struck_nations(nations)

            for user_id, biome in struck:
                label, resource_name, template = BIOME_DISASTERS[biome]

                db.execute(
                    """
                    SELECT ue.quantity FROM user_economy ue
                    JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
                    WHERE ue.user_id = %s AND rd.name = %s
                    """,
                    (user_id, resource_name),
                )
                res_row = db.fetchone()
                current = int(res_row[0]) if res_row and res_row[0] else 0
                loss = compute_disaster_loss(current)
                if loss <= 0:
                    continue

                db.execute(
                    """
                    UPDATE user_economy ue
                    SET quantity = GREATEST(0, ue.quantity - %s)
                    FROM resource_dictionary rd
                    WHERE ue.resource_id = rd.resource_id
                      AND rd.name = %s AND ue.user_id = %s
                    """,
                    (loss, resource_name, user_id),
                )
                db.execute(
                    "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
                    (user_id, f"{label}: " + template.format(amt=f"{loss:,}")),
                )
                log_verbose(
                    f"DISASTER | USER: {user_id} | biome={biome} type={label} "
                    f"resource={resource_name} loss={loss}"
                )

            db.execute(
                "UPDATE task_runs SET last_run = now() WHERE task_name=%s",
                (TASK_NAME,),
            )
        except Exception as e:
            handle_exception(e, TASK_NAME)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, ADVISORY_LOCK_ID)
            except Exception:
                pass
