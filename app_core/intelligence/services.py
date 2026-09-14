import time
import random as rand

import variables
from .repositories import (
    get_unit_quantity,
    decrease_unit_quantity,
    get_username,
    get_spy_reports_for_user,
    touch_defcon,
    get_latest_spy_operation,
    insert_spy_operation,
    get_revealed_values,
    update_revealed_spyinfo,
    has_active_embassy,
    insert_news,
)
from app_core.market.repositories import get_user_resource_quantity, decrement_resource
from app_core.world_affairs.services import log_event

SPY_COOLDOWN_SECONDS = 3600 * 12

# Sabotage/assassination are capped so a single op can't cripple a nation -
# they're meant to be felt, not devastating.
SABOTAGE_LOSS_PCT = 0.05
ASSASSINATION_LOSS_PCT = 0.10
ASSASSINATION_MAX_KILL = 5

VALID_SPY_TYPES = ("units", "resources", "sabotage", "assassinate_spies")


def fetch_spy_reports(db, cId):
    """Raises on failure - the caller (route) decides how to handle it.
    Matches the scope of the original view's try/except, which wrapped
    exactly the cursor + query + dict-conversion, not the sorting in
    sort_spy_reports() below."""
    info = get_spy_reports_for_user(db, cId)
    return [dict(row) for row in info]


def sort_spy_reports(data):
    """Pure data shaping, no DB access. The original didn't wrap this part
    in try/except, so an error here should surface as a real 500 rather
    than silently degrade to an empty page - preserved as-is."""
    sorted_data = {}
    for row in data:
        sorted_data.setdefault(row["spyee"], []).append(row)

    fully_sorted = {}
    for user, rows in sorted_data.items():
        for entry in rows:
            date = entry["date"]
            for k, v in entry.items():
                if entry[k] != "false":
                    if not fully_sorted.get(user, False):
                        fully_sorted[user] = {}
                    if not fully_sorted[user].get(k, False):
                        fully_sorted[user][k] = v
                    if fully_sorted[user].get("date", False):
                        if date > fully_sorted[user]["date"]:
                            fully_sorted[user][k] = v

    required_data = variables.RESOURCES + variables.UNITS
    for resource in required_data:
        for user, entry in fully_sorted.items():
            if resource not in entry:
                fully_sorted[user][resource] = "?"

    return fully_sorted


def get_spy_amount_form_data(db, cId):
    """Returns (your_country_name, current_spy_count) for the /spyAmount GET form."""
    your_country = get_username(db, cId) or ""
    spies = get_unit_quantity(db, cId, "spies")
    return your_country, spies


def submit_spy_amount(db, cId, eId):
    """Original spyAmount POST handler read defcon and the enemy's spy count
    but never used either value - "Removed spoofing and leaking
    functionality" per the original comment. Preserved exactly, dead reads
    included: this migration doesn't change espionage behavior."""
    touch_defcon(db, eId)
    enemy_spies = get_unit_quantity(db, eId, "spies")
    if enemy_spies < 1:
        enemy_spies = 1


def resolve_spy_operation(db, cId, eId, spies, spy_type, keep_private=False):
    """Runs one espionage operation.
    Returns (ok, status_code, error_message, spy_entry) - spy_entry is a dict
    describing the outcome for the attacker (for the /spyResult page), None
    on failure."""
    # Serializes this attacker's spy operations (same pattern as
    # wars/routes.py's drone_strike/cruise_missile_strike). Found
    # 2026-09-13: `actual_spies` below is a stale read with no lock, and
    # decrease_unit_quantity()'s deduction is `GREATEST(0, quantity - %s)`
    # with no `WHERE quantity >= amount` guard -- two concurrent spy
    # operations (same or different target; the 12h cooldown only applies
    # to a *different* target) could both pass the spy-count check and both
    # execute a full operation's real effects (intel reveal, sabotage,
    # assassination) against a target using spies the attacker only had
    # once -- a PvP-fairness bug, not just an economy one.
    db.execute("SELECT pg_advisory_xact_lock(%s)", (cId,))

    if spy_type not in VALID_SPY_TYPES:
        return False, 400, "Invalid spy operation type.", None

    result = get_latest_spy_operation(db, cId)
    spyee, date = result if result else (None, 0)

    current_time = time.time()
    if str(spyee) != str(eId) and current_time - date < SPY_COOLDOWN_SECONDS:
        secs_left = int(current_time - date)
        return False, 400, (
            f"12 hour cooldown for spying on another country. "
            f"{secs_left} seconds left."
        ), None

    if has_active_embassy(db, cId, eId):
        return False, 403, (
            "You cannot spy on a nation you have an active Embassy treaty with."
        ), None

    actual_spies = get_unit_quantity(db, cId, "spies")

    if spies <= 0:
        return False, 400, "Must send at least 1 spy.", None

    if spies > actual_spies:
        missing = actual_spies - spies
        return False, 400, (
            f"You don't have enough spies ({spies}/{actual_spies}). "
            f"Missing {missing} spies"
        ), None

    enemy_spies = get_unit_quantity(db, eId, "spies")

    executed_spies = 0
    uncovered_spies = 0
    uncovered = {}

    operation_id = insert_spy_operation(db, cId, eId, time.time())
    if not operation_id:
        return False, 500, "Failed to record spy operation", None

    if spy_type == "sabotage":
        object_list = variables.RESOURCES
    elif spy_type == "assassinate_spies":
        object_list = ["spies"]
    elif spy_type == "units":
        object_list = variables.UNITS
    else:
        object_list = variables.RESOURCES

    for obj in object_list:
        if spies - executed_spies > 0:
            own_rand = round(rand.uniform(0, 1), 3)
            enemy_rand = round(rand.uniform(0, 1), 3)

            own_score = own_rand * spies
            enemy_score = enemy_rand * enemy_spies

            if own_score == 0:
                own_score = 0.0001
            if enemy_score == 0:
                enemy_score = 0.0001

            multiplier = enemy_score / own_score

            if multiplier > 10:
                executed_spies += 1
            if multiplier > 2:
                uncovered_spies += 1
            if multiplier > 1:  # Enemy won
                uncovered[obj] = False
            elif multiplier <= 1:  # Own won
                uncovered[obj] = True

    uncovered_objects = [k for k, v in uncovered.items() if v]
    news_message = None
    spy_entry = {}
    attacker_name = get_username(db, cId) or "A nation"
    target_name = get_username(db, eId) or "a nation"

    if spy_type == "sabotage":
        sabotaged = []
        for resource in uncovered_objects:
            current_qty = get_user_resource_quantity(db, eId, resource) or 0
            if current_qty > 0:
                loss = max(1, int(current_qty * SABOTAGE_LOSS_PCT))
                if decrement_resource(db, eId, resource, loss):
                    sabotaged.append((resource, loss))
        if sabotaged:
            details = ", ".join(f"{loss} {resource}" for resource, loss in sabotaged)
            # Named directly to the victim so their intel tells them who hit them,
            # regardless of keep_private - that flag only controls the public
            # World Affairs post below, not this personal notification.
            news_message = f"Your nation was sabotaged by {attacker_name}! You lost {details}."
            spy_entry = {resource: f"-{loss}" for resource, loss in sabotaged}
            if not keep_private:
                log_event(
                    db, "sabotage",
                    f"{attacker_name} sabotaged {target_name}'s economy, destroying {details}.",
                    actor_id=cId, target_id=eId,
                )
        else:
            spy_entry = {"message": "Your spies attempted sabotage but couldn't inflict any damage."}
    elif spy_type == "assassinate_spies":
        if uncovered.get("spies"):
            enemy_spy_count = get_unit_quantity(db, eId, "spies")
            kill = min(
                ASSASSINATION_MAX_KILL,
                max(1, int(enemy_spy_count * ASSASSINATION_LOSS_PCT)),
            )
            if enemy_spy_count > 0:
                decrease_unit_quantity(db, eId, "spies", kill)
                news_message = f"{attacker_name}'s agents assassinated {kill} of your spies!"
                spy_entry = {"spies killed": kill}
                if not keep_private:
                    log_event(
                        db, "assassination",
                        f"{attacker_name}'s agents assassinated {kill} of {target_name}'s spies.",
                        actor_id=cId, target_id=eId,
                    )
            else:
                spy_entry = {"message": "The enemy had no spies left to assassinate."}
        else:
            spy_entry = {"message": "Your spies attempted an assassination but were unable to succeed."}
    else:
        if uncovered_objects:
            revealed_map = get_revealed_values(db, eId, uncovered_objects, spy_type)
            update_revealed_spyinfo(db, operation_id, uncovered_objects, revealed_map)
            spy_entry = revealed_map
        else:
            spy_entry = {"message": "Your spies were unable to gather any intelligence this time."}

    if news_message is None and uncovered_spies > 0:
        news_message = f"Foreign spies from {attacker_name} were detected probing your nation's defenses."

    if news_message:
        insert_news(db, eId, news_message)

    if uncovered_spies > 0:
        spy_entry["spies detected by enemy"] = uncovered_spies

    decrease_unit_quantity(db, cId, "spies", executed_spies)

    return True, 200, None, spy_entry
