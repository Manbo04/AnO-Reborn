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
)

SPY_COOLDOWN_SECONDS = 3600 * 12


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


def resolve_spy_operation(db, cId, eId, spies, spy_type):
    """Runs one espionage operation. Returns (ok, status_code, error_message)."""
    result = get_latest_spy_operation(db, cId)
    spyee, date = result if result else (None, 0)

    current_time = time.time()
    if str(spyee) != str(eId) and current_time - date < SPY_COOLDOWN_SECONDS:
        secs_left = int(current_time - date)
        return False, 400, (
            f"12 hour cooldown for spying on another country. "
            f"{secs_left} seconds left."
        )

    if has_active_embassy(db, cId, eId):
        return False, 403, (
            "You cannot spy on a nation you have an active Embassy treaty with."
        )

    actual_spies = get_unit_quantity(db, cId, "spies")

    if spies <= 0:
        return False, 400, "Must send at least 1 spy."

    if spies > actual_spies:
        missing = actual_spies - spies
        return False, 400, (
            f"You don't have enough spies ({spies}/{actual_spies}). "
            f"Missing {missing} spies"
        )

    enemy_spies = get_unit_quantity(db, eId, "spies")

    executed_spies = 0  # TODO: ADD NOTIFICATION FOR THIS
    uncovered_spies = 0  # TODO: ADD NOTIFICATION FOR THIS
    uncovered = {}

    operation_id = insert_spy_operation(db, cId, eId, time.time())
    if not operation_id:
        return False, 500, "Failed to record spy operation"

    object_list = variables.UNITS if spy_type == "units" else variables.RESOURCES

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
    if uncovered_objects:
        revealed_map = get_revealed_values(db, eId, uncovered_objects, spy_type)
        update_revealed_spyinfo(db, operation_id, uncovered_objects, revealed_map)

    decrease_unit_quantity(db, cId, "spies", executed_spies)

    return True, 200, None
