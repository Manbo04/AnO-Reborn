"""War combat mechanics: branch action points, entrenchment, intel, naval blockade (JOB C).

Pure formulas and rules are decoupled from database queries so they can be
unit-tested without a database or running Flask app.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AP_MAX = 12
AP_START = 6
AP_REGEN_PER_HOUR = 1

ENTRENCH_MAX = 3
INTEL_MAX = 100

# Action costs: (branch, cost)
AP_COSTS: Dict[str, Tuple[Optional[str], int]] = {
    "ground_attack": ("ground", 3),
    "air_attack": ("air", 3),
    "naval_attack": ("naval", 3),
    "drone_strike": ("air", 2),
    "cruise_missile_strike": ("naval", 2),
    "dig_in": ("ground", 2),
    "recon_flight": ("air", 2),
    "nuke": (None, 0),
    "strategic_airstrike": (None, 0),
}


# ---------------------------------------------------------------------------
# Pure functions (unit-testable without DB or Flask)
# ---------------------------------------------------------------------------
def get_ap_cost(action: str) -> Tuple[Optional[str], int]:
    """Return (branch, cost) for a given combat action name."""
    norm = action.lower().replace("-", "_").replace(" ", "_")
    return AP_COSTS.get(norm, (None, 0))


def clamp_ap(current_ap: int, gain: int = 1, max_ap: int = AP_MAX) -> int:
    """Clamp AP after regeneration to [0, max_ap]."""
    try:
        val = int(current_ap or 0)
    except (TypeError, ValueError):
        val = 0
    return min(max_ap, max(0, val + gain))


def can_spend_ap(current_ap: int, cost: int) -> bool:
    """Return True if current_ap covers the cost."""
    try:
        val = int(current_ap or 0)
    except (TypeError, ValueError):
        val = 0
    return val >= max(0, int(cost or 0))


def entrenchment_defense_multiplier(level: int) -> float:
    """Calculate defensive strength multiplier for ground units based on entrenchment level.

    Each level gives +10% to GROUND units defensive strength (max level 3 -> +30%).
    """
    try:
        lvl = int(level or 0)
    except (TypeError, ValueError):
        lvl = 0
    clamped_lvl = max(0, min(ENTRENCH_MAX, lvl))
    return 1.0 + 0.10 * clamped_lvl


def intel_attack_multiplier(intel: int) -> float:
    """Calculate attack strength bonus multiplier from intelligence.

    Every attack gets +intel/10 % attack strength (max +10% at 100 intel).
    Formula: 1.0 + (min(10.0, intel / 10.0) / 100.0).
    """
    try:
        val = float(intel or 0)
    except (TypeError, ValueError):
        val = 0.0
    clamped = max(0.0, min(float(INTEL_MAX), val))
    bonus_pct = min(10.0, clamped / 10.0)
    return 1.0 + (bonus_pct / 100.0)


def _ensure_utc(dt: Any) -> Optional[datetime]:
    """Helper to convert dt to timezone-aware UTC datetime."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def is_blockaded(user_id: int, rows: Iterable[Any], now: Optional[datetime] = None) -> bool:
    """Pure function checking if user_id is under an active naval blockade in any war.

    `rows` can be a list of dictionaries or tuples/objects representing active wars.
    Expects fields `attacker`, `defender`, `attacker_blockaded`, `defender_blockaded`.
    """
    info = get_blockade_info(user_id, rows, now)
    return info is not None


def get_blockade_info(
    user_id: int, rows: Iterable[Any], now: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """Return details dict if user_id is blockaded, or None.

    Dict contains {"enemy_id": int, "enemy_name": str, "until": datetime, "formatted_until": str}.
    """
    now_utc = _ensure_utc(now) if now is not None else datetime.now(timezone.utc)
    if not rows:
        return None

    for r in rows:
        attacker_id = None
        defender_id = None
        atk_blockaded = None
        def_blockaded = None
        enemy_name = "Enemy"

        if isinstance(r, dict):
            attacker_id = r.get("attacker")
            defender_id = r.get("defender")
            atk_blockaded = r.get("attacker_blockaded")
            def_blockaded = r.get("defender_blockaded")
            if user_id == attacker_id:
                enemy_name = r.get("defender_name") or r.get("enemy_name") or f"Nation {defender_id}"
            else:
                enemy_name = r.get("attacker_name") or r.get("enemy_name") or f"Nation {attacker_id}"
        elif isinstance(r, (list, tuple)):
            # Fallback for tuple rows with at least attacker, defender, atk_block, def_block
            if len(r) >= 4:
                attacker_id = r[0]
                defender_id = r[1]
                atk_blockaded = r[2]
                def_blockaded = r[3]
                if len(r) >= 5:
                    enemy_name = str(r[4])
        else:
            attacker_id = getattr(r, "attacker", None)
            defender_id = getattr(r, "defender", None)
            atk_blockaded = getattr(r, "attacker_blockaded", None)
            def_blockaded = getattr(r, "defender_blockaded", None)
            enemy_name = getattr(r, "enemy_name", "Enemy")

        until = None
        enemy_id = None
        if user_id == attacker_id:
            until = atk_blockaded
            enemy_id = defender_id
        elif user_id == defender_id:
            until = def_blockaded
            enemy_id = attacker_id

        if until is not None:
            until_utc = _ensure_utc(until)
            if until_utc and until_utc > now_utc:
                return {
                    "enemy_id": enemy_id,
                    "enemy_name": enemy_name,
                    "until": until_utc,
                    "formatted_until": until_utc.strftime("%d %b %H:%M UTC"),
                }

    return None


def parse_one_screen_attack(
    form_data: Dict[str, Any],
    owned_units: Dict[str, int],
    unit_domain_map: Optional[Dict[str, List[str]]] = None,
    unit_costs: Optional[Dict[str, int]] = None,
    available_supplies: int = 2000,
    current_ap: Optional[Dict[str, int]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Pure validation and parser for one-screen attack form submission.

    Returns (parsed_payload, error_message).
    """
    if unit_domain_map is None:
        unit_domain_map = {
            "ground": ["soldiers", "tanks", "artillery"],
            "air": ["fighters", "bombers", "apaches"],
            "naval": ["destroyers", "cruisers", "submarines"],
        }
    if unit_costs is None:
        unit_costs = {
            "soldiers": 1, "tanks": 3, "artillery": 2,
            "fighters": 5, "bombers": 10, "apaches": 5,
            "destroyers": 25, "cruisers": 50, "submarines": 30,
            "icbms": 20, "nukes": 50,
        }

    attack_type = form_data.get("attack_type") or form_data.get("domain") or "ground"

    # Special attack (icbms)
    if attack_type == "special":
        special_unit = form_data.get("special_unit") or "icbms"
        if special_unit == "nukes":
            return {"special": True, "unit": "nukes", "is_nuke": True}, None
        if special_unit not in ("icbms",):
            return None, "Invalid special unit selected"

        amount_str = form_data.get("amount") or form_data.get(special_unit)
        try:
            amount = int(amount_str or 0)
        except (ValueError, TypeError):
            return None, "Unit amount must be a valid number"

        if amount <= 0:
            return None, "Can't attack because you haven't sent any units"

        owned = owned_units.get(special_unit, 0) or 0
        if amount > owned:
            return None, f"You only own {owned} {special_unit}"

        target = form_data.get("targeted_unit") or form_data.get("target")
        all_possible_targets = [u for d_units in unit_domain_map.values() for u in d_units]
        if not target or target not in all_possible_targets:
            return None, "Please select a target unit type"

        return {
            "special": True,
            "unit": special_unit,
            "amount": amount,
            "target": target,
            "units": {special_unit: amount},
        }, None

    # Regular domain attack (ground, air, naval)
    if attack_type not in unit_domain_map:
        return None, "Please select an attack type (Ground, Naval, or Air)"

    domain_units = unit_domain_map[attack_type]
    selected_units = {}
    total_sent = 0
    total_supply_cost = 0

    for u in domain_units:
        raw_val = form_data.get(u, 0)
        try:
            amt = int(raw_val or 0)
        except (ValueError, TypeError):
            return None, "Unit amount entered was not a number"
        if amt < 0:
            return None, "Invalid amount selected!"
        owned = owned_units.get(u, 0) or 0
        if amt > owned:
            return None, f"You only own {owned} {u}"
        selected_units[u] = amt
        total_sent += amt
        total_supply_cost += amt * unit_costs.get(u, 1)

    if total_sent == 0:
        return None, "Can't attack because you haven't sent any units"

    if available_supplies < 200:
        return None, "The minimum supply amount is 200"

    if total_supply_cost > available_supplies:
        return None, f"Not enough supplies available (need {total_supply_cost}, have {available_supplies})"

    # AP check if current_ap passed
    branch, ap_cost = get_ap_cost(f"{attack_type}_attack")
    if current_ap is not None and branch:
        have_ap = current_ap.get(branch, 0)
        if have_ap < ap_cost:
            return None, f"Not enough {branch} action points (have {have_ap}, need {ap_cost}). +1 every hour."

    return {
        "special": False,
        "domain": attack_type,
        "units": selected_units,
        "supply_cost": total_supply_cost,
        "ap_branch": branch,
        "ap_cost": ap_cost,
    }, None


# ---------------------------------------------------------------------------
# Database helpers (with graceful schema degradation)
# ---------------------------------------------------------------------------
_COLUMNS_EXIST_CACHE: Optional[bool] = None


def war_combat_columns_exist(db) -> bool:
    """Check if the JOB C columns exist on the wars table."""
    global _COLUMNS_EXIST_CACHE
    if _COLUMNS_EXIST_CACHE is not None:
        return _COLUMNS_EXIST_CACHE
    try:
        db.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'wars' AND column_name = 'attacker_ground_ap'
            LIMIT 1
            """
        )
        exists = db.fetchone() is not None
    except Exception:
        return False
    # Only cache a positive answer, so the columns are picked up as soon as
    # the migration has run without needing a restart.
    if exists:
        _COLUMNS_EXIST_CACHE = True
    return exists


def get_combatant_role(db, war_id: int, user_id: int) -> Optional[str]:
    """Return 'attacker' or 'defender' depending on user_id's side in war_id."""
    db.execute("SELECT attacker, defender FROM wars WHERE id = %s", (war_id,))
    row = db.fetchone()
    if not row:
        return None
    atk, dfn = row[0], row[1]
    if user_id == atk:
        return "attacker"
    if user_id == dfn:
        return "defender"
    return None


def spend_action_points(
    db, war_id: int, user_id: int, branch: str, cost: int
) -> Tuple[bool, Optional[str]]:
    """Atomically spend action points for a combat action.

    Returns (success: bool, error_message: Optional[str]).
    """
    if cost <= 0:
        return True, None
    # branch goes into a column name below: whitelist it.
    if branch not in ("ground", "air", "naval"):
        return True, None

    if not war_combat_columns_exist(db):
        return True, None

    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return False, "You are not a participant in this war."

    col = f"{role}_{branch}_ap"
    db.execute(
        f"""
        UPDATE wars
        SET {col} = {col} - %s
        WHERE id = %s AND {col} >= %s
        RETURNING {col}
        """,
        (cost, war_id, cost),
    )
    row = db.fetchone()
    if row is not None:
        return True, None

    # Not enough AP: fetch current value for friendly message
    db.execute(f"SELECT COALESCE({col}, 0) FROM wars WHERE id = %s", (war_id,))
    cur_row = db.fetchone()
    have = int(cur_row[0] or 0) if cur_row else 0
    return False, f"Not enough {branch} action points (have {have}, need {cost}). +1 every hour."


def dig_in(db, war_id: int, user_id: int) -> Tuple[bool, Optional[str], int]:
    """Execute 'Dig In' action (costs 2 ground AP, +1 level up to 3).

    Returns (success, message, new_level).
    """
    if not war_combat_columns_exist(db):
        return False, "Combat upgrades not yet available", 0

    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return False, "You are not a participant in this war.", 0

    entrench_col = f"{role}_entrench"
    db.execute(f"SELECT COALESCE({entrench_col}, 0) FROM wars WHERE id = %s", (war_id,))
    row = db.fetchone()
    current_level = int(row[0] or 0) if row else 0

    if current_level >= ENTRENCH_MAX:
        return False, f"Already at maximum entrenchment level ({ENTRENCH_MAX}).", current_level

    # Spend 2 ground AP atomically
    ok, err = spend_action_points(db, war_id, user_id, "ground", 2)
    if not ok:
        return False, err or "Not enough ground action points.", current_level

    db.execute(
        f"""
        UPDATE wars
        SET {entrench_col} = LEAST(%s, {entrench_col} + 1)
        WHERE id = %s
        RETURNING {entrench_col}
        """,
        (ENTRENCH_MAX, war_id),
    )
    res = db.fetchone()
    new_lvl = int(res[0]) if res else current_level + 1
    return True, f"Dug in! Entrenchment increased to level {new_lvl} (+{new_lvl * 10}% ground defense).", new_lvl


def recon_flight(db, war_id: int, user_id: int) -> Tuple[bool, Optional[str], int]:
    """Execute 'Recon Flight' action (costs 2 air AP, requires >= 1 fighter/bomber, gives +25 intel).

    Returns (success, message, new_intel).
    """
    if not war_combat_columns_exist(db):
        return False, "Combat upgrades not yet available", 0

    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return False, "You are not a participant in this war.", 0

    # Verify at least 1 fighter or bomber owned
    db.execute(
        """
        SELECT COALESCE(SUM(um.quantity), 0)
        FROM user_military um
        JOIN unit_dictionary ud ON um.unit_id = ud.unit_id
        WHERE um.user_id = %s AND ud.name IN ('fighters', 'bombers') AND ud.is_active = TRUE
        """,
        (user_id,),
    )
    aircraft_count = int(db.fetchone()[0] or 0)
    if aircraft_count < 1:
        return False, "You need at least 1 fighter jet or bomber to launch a recon flight.", 0

    # Spend 2 air AP
    ok, err = spend_action_points(db, war_id, user_id, "air", 2)
    if not ok:
        return False, err or "Not enough air action points.", 0

    intel_col = f"{role}_intel"
    db.execute(
        f"""
        UPDATE wars
        SET {intel_col} = LEAST(%s, {intel_col} + 25)
        WHERE id = %s
        RETURNING {intel_col}
        """,
        (INTEL_MAX, war_id),
    )
    res = db.fetchone()
    new_intel = int(res[0]) if res else 25
    return True, f"Recon flight completed successfully! Intel increased to {new_intel}/100.", new_intel


def reset_entrenchment_on_ground_attack(db, war_id: int, user_id: int) -> None:
    """Reset entrenchment to 0 when launching your own ground attack."""
    if not war_combat_columns_exist(db):
        return
    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return
    entrench_col = f"{role}_entrench"
    db.execute(f"UPDATE wars SET {entrench_col} = 0 WHERE id = %s", (war_id,))


def consume_intel_on_attack(db, war_id: int, user_id: int) -> int:
    """Consume 25 intel (floor 0) on attack and return the pre-attack intel level."""
    if not war_combat_columns_exist(db):
        return 0
    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return 0
    intel_col = f"{role}_intel"
    db.execute(f"SELECT COALESCE({intel_col}, 0) FROM wars WHERE id = %s", (war_id,))
    row = db.fetchone()
    pre_intel = int(row[0] or 0) if row else 0

    db.execute(
        f"UPDATE wars SET {intel_col} = GREATEST(0, {intel_col} - 25) WHERE id = %s",
        (war_id,),
    )
    return pre_intel


def apply_naval_blockade(db, war_id: int, loser_id: int) -> None:
    """Blockade loser for 24h following a qualifying naval victory."""
    if not war_combat_columns_exist(db):
        return
    role = get_combatant_role(db, war_id, loser_id)
    if not role:
        return
    block_col = f"{role}_blockaded"
    db.execute(
        f"UPDATE wars SET {block_col} = NOW() + INTERVAL '24 hours' WHERE id = %s",
        (war_id,),
    )


def lift_naval_blockade(db, war_id: int, user_id: int) -> None:
    """Lift blockade early if blockaded side wins any naval battle in this war."""
    if not war_combat_columns_exist(db):
        return
    role = get_combatant_role(db, war_id, user_id)
    if not role:
        return
    block_col = f"{role}_blockaded"
    db.execute(f"UPDATE wars SET {block_col} = NULL WHERE id = %s", (war_id,))


def add_spy_intel_on_success(db, cId: int, eId: int, amount: int = 20) -> None:
    """Grant +20 intel to active war when spy mission against war enemy succeeds."""
    if not war_combat_columns_exist(db):
        return
    db.execute(
        """
        SELECT id, attacker, defender FROM wars
        WHERE ((attacker = %s AND defender = %s) OR (attacker = %s AND defender = %s))
          AND status = 'active' AND peace_date IS NULL
        """,
        (cId, eId, eId, cId),
    )
    row = db.fetchone()
    if not row:
        return
    war_id, attacker, defender = row[0], row[1], row[2]
    role = "attacker" if cId == attacker else "defender"
    intel_col = f"{role}_intel"
    db.execute(
        f"UPDATE wars SET {intel_col} = LEAST(%s, {intel_col} + %s) WHERE id = %s",
        (INTEL_MAX, amount, war_id),
    )


def get_war_combat_status(db, war_id: int, user_id: int) -> Dict[str, Any]:
    """Fetch AP, entrenchment, intel, and blockade info for war_attack page."""
    status: Dict[str, Any] = {
        "ground_ap": 6,
        "air_ap": 6,
        "naval_ap": 6,
        "ap_max": AP_MAX,
        "my_entrench": 0,
        "enemy_entrench": 0,
        "my_intel": 0,
        "enemy_intel": 0,
        "is_blockaded": False,
        "blockade_until": None,
        "enemy_blockaded": False,
        "enemy_units_revealed": False,
        "enemy_units": {},
    }
    if not war_combat_columns_exist(db):
        return status

    db.execute(
        """
        SELECT attacker, defender,
               attacker_ground_ap, attacker_air_ap, attacker_naval_ap,
               defender_ground_ap, defender_air_ap, defender_naval_ap,
               attacker_entrench, defender_entrench,
               attacker_intel, defender_intel,
               attacker_blockaded, defender_blockaded
        FROM wars WHERE id = %s
        """,
        (war_id,),
    )
    row = db.fetchone()
    if not row:
        return status

    (
        atk, dfn,
        atk_g_ap, atk_a_ap, atk_n_ap,
        dfn_g_ap, dfn_a_ap, dfn_n_ap,
        atk_entrench, dfn_entrench,
        atk_intel, dfn_intel,
        atk_block, dfn_block,
    ) = row

    now_utc = datetime.now(timezone.utc)
    if user_id == atk:
        status["ground_ap"] = atk_g_ap
        status["air_ap"] = atk_a_ap
        status["naval_ap"] = atk_n_ap
        status["my_entrench"] = atk_entrench
        status["enemy_entrench"] = dfn_entrench
        status["my_intel"] = atk_intel
        status["enemy_intel"] = dfn_intel
        if atk_block and _ensure_utc(atk_block) > now_utc:
            status["is_blockaded"] = True
            status["blockade_until"] = _ensure_utc(atk_block).strftime("%d %b %H:%M UTC")
        if dfn_block and _ensure_utc(dfn_block) > now_utc:
            status["enemy_blockaded"] = True
        enemy_id = dfn
    elif user_id == dfn:
        status["ground_ap"] = dfn_g_ap
        status["air_ap"] = dfn_a_ap
        status["naval_ap"] = dfn_n_ap
        status["my_entrench"] = dfn_entrench
        status["enemy_entrench"] = atk_entrench
        status["my_intel"] = dfn_intel
        status["enemy_intel"] = atk_intel
        if dfn_block and _ensure_utc(dfn_block) > now_utc:
            status["is_blockaded"] = True
            status["blockade_until"] = _ensure_utc(dfn_block).strftime("%d %b %H:%M UTC")
        if atk_block and _ensure_utc(atk_block) > now_utc:
            status["enemy_blockaded"] = True
        enemy_id = atk
    else:
        return status

    # If intel >= 50, fetch enemy unit counts
    if status["my_intel"] >= 50:
        status["enemy_units_revealed"] = True
        db.execute(
            """
            SELECT LOWER(ud.name), COALESCE(um.quantity, 0)
            FROM unit_dictionary ud
            LEFT JOIN user_military um ON um.unit_id = ud.unit_id AND um.user_id = %s
            WHERE ud.is_active = TRUE
            """,
            (enemy_id,),
        )
        status["enemy_units"] = {r[0]: int(r[1]) for r in db.fetchall()}

    return status


def check_user_blockaded_market(db, user_id: int) -> Optional[str]:
    """Check if user_id is blockaded in any active war for market enforcement.

    Returns error message string if blockaded, or None.
    """
    if not war_combat_columns_exist(db):
        return None

    db.execute(
        """
        SELECT w.id, w.attacker, w.defender, w.attacker_blockaded, w.defender_blockaded,
               u_atk.username AS attacker_name, u_dfn.username AS defender_name
        FROM wars w
        LEFT JOIN users u_atk ON u_atk.id = w.attacker
        LEFT JOIN users u_dfn ON u_dfn.id = w.defender
        WHERE (w.attacker = %s OR w.defender = %s)
          AND w.status = 'active' AND w.peace_date IS NULL
          AND (w.attacker_blockaded > NOW() OR w.defender_blockaded > NOW())
        """,
        (user_id, user_id),
    )
    rows = db.fetchall()
    now_utc = datetime.now(timezone.utc)
    for r in rows:
        war_id, atk, dfn, atk_block, dfn_block, atk_name, dfn_name = r
        if user_id == atk and atk_block:
            until_utc = _ensure_utc(atk_block)
            if until_utc and until_utc > now_utc:
                return f"Your ports are blockaded (war with {dfn_name or 'Enemy'}) until {until_utc.strftime('%d %b %H:%M UTC')}."
        elif user_id == dfn and dfn_block:
            until_utc = _ensure_utc(dfn_block)
            if until_utc and until_utc > now_utc:
                return f"Your ports are blockaded (war with {atk_name or 'Enemy'}) until {until_utc.strftime('%d %b %H:%M UTC')}."
    return None
