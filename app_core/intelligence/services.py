import math
import time
import random as rand

import variables
from .repositories import (
    get_unit_quantity,
    decrease_unit_quantity,
    get_username,
    get_spy_reports_for_user,
    get_last_spy_op_times,
    get_counter_intel_agents,
    insert_spy_operation,
    get_revealed_values,
    update_revealed_spyinfo,
    has_active_embassy,
    insert_news,
)
from app_core.market.repositories import get_user_resource_quantity, decrement_resource
from app_core.world_affairs.services import log_event

# ---------------------------------------------------------------------------
# Per-operation cooldowns (seconds), per attacker, regardless of target.
# Discord #military-recommendations 2026-09-16 (germanicusjuliuscaesar):
# recon and resource sabotage can be repeated, assassination and sabotage of
# strategic assets (missiles/nukes) are throttled hard. Recon keeps a short
# anti-spam throttle so nobody can script-spam the endpoint.
# This table is the single source of truth: enforcement in
# resolve_spy_operation() and the cooldown display in the UI both read it via
# compute_op_cooldowns().
# ---------------------------------------------------------------------------
SPY_OP_COOLDOWNS = {
    "units": 5 * 60,                    # recon: 5 min anti-spam throttle
    "resources": 5 * 60,                # recon: 5 min anti-spam throttle
    "sabotage": 3 * 3600,               # resource sabotage: 3 h
    "sabotage_strategic": 12 * 3600,    # missiles/nukes sabotage: 12 h
    "assassinate_spies": 12 * 3600,     # assassination: 12 h
}

SPY_OP_LABELS = {
    "units": "Spy on unit amounts",
    "resources": "Spy on resources",
    "sabotage": "Sabotage resources",
    "sabotage_strategic": "Sabotage missiles & nukes",
    "assassinate_spies": "Assassinate spies",
}

VALID_SPY_TYPES = tuple(SPY_OP_COOLDOWNS)

# Sabotage/assassination are capped so a single op can't cripple a nation -
# they're meant to be felt, not devastating.
SABOTAGE_LOSS_PCT = 0.05
ASSASSINATION_LOSS_PCT = 0.10
ASSASSINATION_MAX_KILL = 5
# Strategic sabotage destroys at most this many units per successful op
# (one strategic unit type, picked among the ones the spies got to).
STRATEGIC_SABOTAGE_TARGETS = ("icbms", "nukes", "cruise_missiles")
STRATEGIC_SABOTAGE_MAX_DESTROYED = 1

# ---------------------------------------------------------------------------
# Counter-intelligence (defender-side, runs BEFORE the operation executes).
# interception chance = CI_MAX_INTERCEPT * (1 - exp(-CI_STRENGTH_K * agents / spies_sent))
#   - 0 agents -> 0%; diminishing returns as agents grow; hard cap 60%.
#   - scales against the number of spies the attacker commits, so a bigger
#     operation is harder to stop.
#   e.g. agents == spies sent -> ~24%, 3x -> ~47%, 10x -> ~60% (cap).
# On interception the op does nothing, CI_CAPTURE_PCT of the spies sent are
# captured/killed (at least 1), the rest are driven off and return home.
# ---------------------------------------------------------------------------
COUNTER_INTEL_UNIT = "counter_intel_agents"
CI_MAX_INTERCEPT = 0.60
CI_STRENGTH_K = 0.5
CI_CAPTURE_PCT = 0.40


def compute_op_cooldowns(last_times, now=None):
    """{spy_type: seconds_left} for every op type (0 = ready).
    last_times is get_last_spy_op_times()'s {spy_type|None: date}; the None
    key (rows from before migration 0085, op type unknown) counts against
    every type so the migration doesn't hand out a free cooldown reset."""
    now = time.time() if now is None else now
    legacy = last_times.get(None) or 0
    result = {}
    for op, cooldown in SPY_OP_COOLDOWNS.items():
        last = max(last_times.get(op) or 0, legacy)
        left = int(cooldown - (now - last)) if last else 0
        result[op] = max(0, left)
    return result


def format_cooldown(seconds):
    """Short human string for a cooldown: '2h 05m', '4m 10s', 'ready'."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "ready"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def get_spy_op_status(db, cId, now=None):
    """UI helper: list of {type, label, cooldown, seconds_left, ready,
    remaining} for every op type, in SPY_OP_COOLDOWNS order."""
    left = compute_op_cooldowns(get_last_spy_op_times(db, cId), now)
    return [
        {
            "type": op,
            "label": SPY_OP_LABELS[op],
            "cooldown": format_cooldown(SPY_OP_COOLDOWNS[op]),
            "seconds_left": left[op],
            "ready": left[op] == 0,
            "remaining": format_cooldown(left[op]),
        }
        for op in SPY_OP_COOLDOWNS
    ]


def counter_intel_intercept_chance(agents, spies_sent):
    """Probability (0..CI_MAX_INTERCEPT) that the defender's counter-intel
    agents stop an operation of `spies_sent` spies before it executes."""
    agents = max(0, int(agents or 0))
    spies_sent = max(1, int(spies_sent or 0))
    if agents == 0:
        return 0.0
    chance = CI_MAX_INTERCEPT * (1 - math.exp(-CI_STRENGTH_K * agents / spies_sent))
    return min(CI_MAX_INTERCEPT, max(0.0, chance))


def counter_intel_captured(spies_sent):
    """How many of the attacker's spies are captured/killed on interception."""
    spies_sent = max(0, int(spies_sent or 0))
    if spies_sent == 0:
        return 0
    return min(spies_sent, max(1, int(spies_sent * CI_CAPTURE_PCT)))


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

    required_data = ["money"] + variables.RESOURCES + variables.UNITS
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
    # operations could both pass the spy-count check and both execute a
    # full operation's real effects (intel reveal, sabotage, assassination)
    # against a target using spies the attacker only had once -- a
    # PvP-fairness bug, not just an economy one.
    db.execute("SELECT pg_advisory_xact_lock(%s)", (cId,))

    if spy_type not in VALID_SPY_TYPES:
        return False, 400, "Invalid spy operation type.", None

    current_time = time.time()
    # Per-op-type cooldown, regardless of target (2026-09-16 fix kept: a
    # player can't dodge it by hitting the same rival repeatedly). Each op
    # type has its own timer from SPY_OP_COOLDOWNS (migration 0085 added
    # spyinfo.spy_type so the timers can be told apart).
    secs_left = compute_op_cooldowns(
        get_last_spy_op_times(db, cId), current_time
    )[spy_type]
    if secs_left > 0:
        return False, 400, (
            f"{SPY_OP_LABELS[spy_type]} is on cooldown "
            f"({format_cooldown(SPY_OP_COOLDOWNS[spy_type])} between uses). "
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
        missing = spies - actual_spies
        return False, 400, (
            f"You don't have enough spies ({spies}/{actual_spies}). "
            f"Missing {missing} spies"
        ), None

    attacker_name = get_username(db, cId) or "A nation"
    target_name = get_username(db, eId) or "a nation"

    # --- Counter-intelligence: pre-execution interception -----------------
    # Runs before the spy-vs-spy contest below. If it fires, the operation
    # never executes (no reveal, no sabotage, no assassination); the only
    # side effects are the recorded attempt (consumes the cooldown), the
    # captured spies, and a report to both sides. Returns early, so the
    # single spy deduction at the bottom of this function can't also run.
    ci_agents = get_counter_intel_agents(db, eId)
    intercept_chance = counter_intel_intercept_chance(ci_agents, spies)
    if intercept_chance > 0 and rand.random() < intercept_chance:
        operation_id = insert_spy_operation(
            db, cId, eId, current_time, spy_type, intercepted=True
        )
        if not operation_id:
            return False, 500, "Failed to record spy operation", None
        captured = counter_intel_captured(spies)
        decrease_unit_quantity(db, cId, "spies", captured)
        driven_off = spies - captured
        insert_news(
            db, eId,
            f"Your counter-intelligence foiled an operation by {attacker_name} "
            f"({SPY_OP_LABELS[spy_type].lower()}). {captured} enemy spies were "
            f"captured and the rest were driven off.",
        )
        insert_news(
            db, cId,
            f"Your operation against {target_name} "
            f"({SPY_OP_LABELS[spy_type].lower()}) was intercepted by their "
            f"counter-intelligence. {captured} of your spies were captured.",
        )
        return True, 200, None, {
            "message": (
                f"Operation failed: {target_name}'s counter-intelligence "
                f"intercepted your spies before they could act."
            ),
            "spies captured": captured,
            "spies returned home": driven_off,
        }

    enemy_spies = get_unit_quantity(db, eId, "spies")

    executed_spies = 0
    uncovered_spies = 0
    uncovered = {}

    operation_id = insert_spy_operation(db, cId, eId, current_time, spy_type)
    if not operation_id:
        return False, 500, "Failed to record spy operation", None

    if spy_type == "sabotage":
        object_list = variables.RESOURCES
    elif spy_type == "sabotage_strategic":
        object_list = list(STRATEGIC_SABOTAGE_TARGETS)
    elif spy_type == "assassinate_spies":
        object_list = ["spies"]
    elif spy_type == "units":
        object_list = variables.UNITS + ["iron_domes"]
    else:
        object_list = ["money"] + variables.RESOURCES

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
    elif spy_type == "sabotage_strategic":
        # Only among the strategic unit types the spies got to (won the
        # contest for) and the target actually has; destroys at most
        # STRATEGIC_SABOTAGE_MAX_DESTROYED of a single type.
        candidates = [
            (unit, qty) for unit in uncovered_objects
            for qty in [get_unit_quantity(db, eId, unit)] if qty > 0
        ]
        if candidates:
            unit, qty = rand.choice(candidates)
            destroyed = min(qty, STRATEGIC_SABOTAGE_MAX_DESTROYED)
            decrease_unit_quantity(db, eId, unit, destroyed)
            label = unit.replace("_", " ")
            news_message = (
                f"Your nation was sabotaged by {attacker_name}! "
                f"{destroyed} of your {label} were destroyed."
            )
            spy_entry = {f"{label} destroyed": destroyed}
            if not keep_private:
                log_event(
                    db, "sabotage",
                    f"{attacker_name} sabotaged {target_name}'s strategic arsenal, "
                    f"destroying {destroyed} {label}.",
                    actor_id=cId, target_id=eId,
                )
        else:
            spy_entry = {"message": "Your spies couldn't get to any missiles or nukes."}
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
            if "iron_domes" in uncovered_objects:
                db.execute(
                    "SELECT COALESCE(SUM(d.quantity), 0) FROM province_iron_domes d "
                    "JOIN provinces p ON p.id = d.province_id WHERE p.userid = %s",
                    (eId,),
                )
                revealed_map["iron_domes"] = int(db.fetchone()[0])
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

    if uncovered_objects:
        try:
            from wars.action_points import add_spy_intel_on_success
            add_spy_intel_on_success(db, cId, eId, amount=20)
        except Exception:
            pass

    return True, 200, None, spy_entry

