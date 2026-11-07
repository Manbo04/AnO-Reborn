# War: declaration, battle resolution, morale, loot, end

## Order of operations (one ground/air/naval attack)
1. Spend branch action points (wars/action_points.py:116-160 `spend_action_points`; costs `AP_COSTS` at action_points.py:15-25).
2. `Military.fight` (attack_scripts/Nations.py:785): rolls `random.uniform(1, 5)` per side (Nations.py:799, 804) + unit-amount bonus + matchup bonus -> modifiers -> empty-side rule -> winner.
3. Casualties and morale persisted (attack_scripts/war_orchestrator.py:313 `persist_fight_results`); morale <= 0 calls `conclude_war` (spoils).
4. Back in the route: intel consumed, entrenchment reset, war-type damage/loot, infra damage, aftermath (wars/routes.py:1500-1640).

## Constants
### Action points
**Exact rule** (verbatim) - **Source:** `wars/action_points.py:11-26`
```python
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
```
**Notes:** regen +1 per branch per hour via global_tick (app_core/game_ticks/maintenance.py:638-651); DB default 6 per branch (migrations/20261010_1530_war_combat_mechanics_c.sql:5-9).

### Entrenchment and intel
**Exact rule** (verbatim) - **Source:** `wars/action_points.py:47-58`
```python
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
```
**Exact rule** (verbatim) - **Source:** `wars/action_points.py:61-72`
```python
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

```
**Units/range:** +10%/level to ground defence (max 3); attacker intel gives up to +10% attack (intel/10 %); each attack consumes 25 intel (action_points.py:253-269); recon/spy add intel (spy op +20, action_points.py:297).

### Unit-amount bonus and matchup bonus
**Exact rule** (verbatim) - **Source:** `attack_scripts/combat_helpers.py:37-47`
```python
def compute_unit_amount_bonus(
    selected_units_list: list, selected_units: Dict[str, int]
) -> float:
    """Compute the unit-amount-derived bonus used in combat loops.

    Mirrors the original logic in `Nations.fight`: sum(unit_count/150)
    """
    total = 0.0
    for unit in selected_units_list:
        total += (selected_units.get(unit, 0) or 0) / 150.0
    return total
```
**Exact rule** (verbatim) - **Source:** `attack_scripts/nations_helpers.py:11-29`
```python
def calculate_bonuses(attack_effects: Any, enemy_object: Any, target: str) -> float:
    """Compute the fractional bonus contribution from an attack effect.

    This was previously defined inside `attack_scripts/Nations.py` and is a
    pure helper that depends only on `attack_effects` and a small
    `enemy_object` shape (must expose `selected_units: Mapping[str, int]`).

    Returns a small float (e.g. 0.05) suitable for additive bonus math.
    """
    defending_unit_amount = enemy_object.selected_units[target]
    enemy_units_total_amount = sum(enemy_object.selected_units.values())

    # percentage of the enemy's relevant unit type in the force
    unit_of_army = (defending_unit_amount * 100) / (enemy_units_total_amount + 1)

    # scale by the attack_effects magnitude and normalize
    affected_bonus = attack_effects[1] * (unit_of_army / 100)

    return affected_bonus / 100
```
**Units/range:** unit-amount bonus = sum(units sent / 150). Matchup bonus = `attack_effects[1] * share_of_enemy_type / 100`, `/100` again.

### Winner, win_type, casualties
**Exact rule** (verbatim) - **Source:** `attack_scripts/combat_helpers.py:218-267`
```python
def zero_out_empty_side(
    attacker_chance: float,
    defender_chance: float,
    attacker_unit_amount_bonuses: float,
    defender_unit_amount_bonuses: float,
) -> tuple:
    """A side with no effective force gets zero chance.

    The attacker check comes FIRST: an attacker with nothing usable (e.g. only
    units whose upkeep ran out, which contribute no presence bonus) must not
    win just because the defender also has nothing in that domain. Previously
    the empty-defender rule ran first, so such an attack counted as a free win
    (loot, razing, morale damage). With both sides empty the defender holds.

    Returns (attacker_chance, defender_chance)."""
    if attacker_unit_amount_bonuses == 0:
        return 0, defender_chance
    if defender_unit_amount_bonuses == 0:
        return attacker_chance, 0
    return attacker_chance, defender_chance


def resolve_battle_outcome(
    attacker_chance: float,
    defender_chance: float,
    attacker_unit_amount_bonuses: float,
    defender_unit_amount_bonuses: float,
) -> tuple:
    """Determine winner/loser, win_type and winner_casulties using original logic.

    Returns: (winner_is_defender: bool, win_type: float, winner_casulties: float)
    """
    if defender_chance >= attacker_chance:
        # defender wins
        if attacker_unit_amount_bonuses == 0:
            return True, 5, 0
        return (
            True,
            (defender_chance / attacker_chance),
            ((1 + attacker_chance) / defender_chance),
        )
    else:
        # attacker wins
        if defender_unit_amount_bonuses == 0:
            return False, 5, 0
        return (
            False,
            (attacker_chance / defender_chance),
            ((1 + defender_chance) / attacker_chance),
        )
```
**Exact rule** (verbatim) - **Source:** `attack_scripts/combat_helpers.py:270-317`
```python
# Casualty tuning (share of the committed force of each unit type)
WINNER_LOSS_PER_POINT = 0.04
WINNER_MAX_LOSS_FRAC = 0.30
LOSER_LOSS_PER_POINT = 0.05
LOSER_MAX_LOSS_FRAC = 0.50


def compute_unit_casualties(
    winner_casulties: float,
    win_type: float,
    winner_units_list: list,
    loser_units_list: list,
    winner_units: dict = None,
    loser_units: dict = None,
    rng: object = None,
) -> tuple:
    """Compute casualty values for each unit pair in the engagement.

    `winner_units`/`loser_units` map unit_type -> amount actually committed to this
    fight (i.e. `Units.selected_units`). A unit type present in the composition list
    but sent with amount 0 takes no casualties, and casualties for a sent unit type
    are capped at the amount sent — a side can never lose more of a unit type than it
    actually committed to this specific engagement, regardless of total stockpile.

    Returns two lists of (unit_name, casualties) for winner and loser respectively.
    The function is pure if a deterministic RNG is provided (useful for tests).
    """
    import random as _random

    _rng = rng or _random
    winner_units = winner_units or {}
    loser_units = loser_units or {}
    winner_pairs = []
    loser_pairs = []

    for w_unit in winner_units_list:
        w_sent = winner_units.get(w_unit, 0) or 0
        if w_sent > 0:
            w_frac = min(WINNER_MAX_LOSS_FRAC, WINNER_LOSS_PER_POINT * winner_casulties)
            w_cas = min(w_sent, max(1, round(w_sent * w_frac * _rng.uniform(0.7, 1.3))))
            winner_pairs.append((w_unit, w_cas))

    for l_unit in loser_units_list:
        l_sent = loser_units.get(l_unit, 0) or 0
        if l_sent > 0:
            l_frac = min(LOSER_MAX_LOSS_FRAC, LOSER_LOSS_PER_POINT * win_type)
            l_cas = min(l_sent, max(1, round(l_sent * l_frac * _rng.uniform(0.8, 1.2))))
            loser_pairs.append((l_unit, l_cas))
```
**Notes:** defender wins ties (`>=`). A side with 0 effective unit amount cannot win; win_type 5 when the opposing side is empty.

### Morale drop (what is actually applied)
**Exact rule** (verbatim) - **Source:** `attack_scripts/war_orchestrator.py:142-149`
```python
def _determine_win_label(win_type: Optional[int]) -> str:
    if win_type is None:
        return "close victory"
    if win_type >= 3:
        return "annihilation"
    if win_type >= 2:
        return "definite victory"
    return "close victory"
```
**Exact rule** (verbatim) - **Source:** `attack_scripts/war_orchestrator.py:379-397`
```python
            # If the attacker lost, attacker morale does not drop (morale_delta = 0).
            # "Attacker" = whoever launched THIS battle (counter-attacks
            # included), not the war's original aggressor (morale_column).
            is_attacker_loss = bool(
                attacker_lost or getattr(loser, "_attacker_lost", False)
            )
            if is_attacker_loss:
                morale_delta = 0
            elif win_type is not None:
                # (Legacy compatibility) The old code checked if `win_type >= 4`
                # and applied fixed morale drops instead of `computed_morale_delta`.
                if win_type >= 4:
                    morale_delta = 20
                elif win_type >= 3:
                    morale_delta = 15
                elif win_type >= 2:
                    morale_delta = 10
                else:
                    morale_delta = 5
```
**Units/range:** attacker lost -> 0 morale lost. Otherwise by win_type: >=4 -> 20, >=3 -> 15, >=2 -> 10, else 5. Starting morale default 100 (db/schema.sql:4201).
**Notes:** STALE/DEAD: `compute_morale_delta` (combat_helpers.py:174-215, up to 200) and the `unit_morale_weights` dict in `Military.fight` are only used when `win_type is None`, and `fight()` always passes a win_type. Labels: win_type >=3 annihilation, >=2 definite victory, else close victory. Also note labels (3) vs morale table (4) use different thresholds.

### Blockade
**Exact rule** (verbatim) - **Source:** `wars/action_points.py:272-283`
```python
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
```
**Notes:** naval win with definite victory/annihilation blockades the loser 24h; lifted if the blockaded side wins a naval battle (Nations.py `fight`).

### War types: Raze / Sustained / Loot
**Exact rule** (verbatim) - **Source:** `wars/routes.py:1514-1520`
```python
            if war_type:
                attack_effects = list(attack_effects)
                if war_type == "Raze":
                    attack_effects[0] = attack_effects[0] * 10
                elif war_type == "Loot":
                    attack_effects[0] = attack_effects[0] * 0.2
                    # Treasury loot is a ground raid; air and naval wins cannot seize it.
```
**Exact rule** (verbatim) - **Source:** `wars/routes.py:1548-1558`
```python
                            from app_core.bots import BOT_AUTH_TYPE

                            loot_frac = (
                                BOT_LOOT_FRACTION
                                if _auth_row and _auth_row[0] == BOT_AUTH_TYPE
                                else 0.1
                            )
                            max_loot = int(math.floor(max(0, available_resource * loot_frac)))
                            if max_loot < 0:
                                max_loot = 0
                            loot = random.randint(0, max_loot)
```
**Exact rule** (verbatim) - **Source:** `wars/routes.py:1589-1592`
```python
                    destroy_frac = {"Raze": 0.25, "Sustained": 0.08, "Loot": 0.03}.get(
                        war_type, 0.08
                    )
                    infra_damage_effects = Military.infrastructure_damage(
```
**Exact rule** (verbatim) - **Source:** `wars/routes.py:370`
```python
BOT_LOOT_FRACTION = 0.02
```
**Units/range:** damage points x10 (Raze) or x0.2 (Loot); max share of the hit province's buildings one attack can destroy: Raze 25%, Sustained 8%, Loot 3%; one building costs 1500 damage points (Nations.py:489). Loot war: ground win steals `randint(0, 10% of defender gold)` (2% against bot nations).

### War end spoils (morale zero or surrender)
**Exact rule** (verbatim) - **Source:** `attack_scripts/war_orchestrator.py:244-247`
```python
    loot_multiplier = 0.3 if winner_upgrades.get("lootingteams") else 0.2
    from wars import rules as war_rules

    loot_multiplier = war_rules.surrender_spoils_rate(surrender_kind, loot_multiplier)
```
**Exact rule** (verbatim) - **Source:** `wars/rules.py:29-43`
```python
WAR_MIN_DURATION_SECONDS = 24 * HOUR
TRUCE_SECONDS = 3 * DAY
DEFENDER_COOLDOWN_SECONDS = 24 * HOUR

SURRENDER_KINDS = ("conditional", "unconditional")
CONDITIONAL_SURRENDER_SPOILS = 0.10  # share of each resource (standard: 20%)
UNCONDITIONAL_SURRENDER_MANPOWER_FACTOR = 0.5
UNCONDITIONAL_SURRENDER_PENALTY_SECONDS = 5 * DAY
PENALTY_MANPOWER_CAP = "manpower_cap"

WAR_ORIGIN_DECLARED = "declared"
WAR_ORIGIN_MDP_JOIN = "mdp_join"

MAX_NUKE_VOLLEYS_PER_WAR = 1
RADIATION_DAMAGE_MULTIPLIER = 0.5
```
**Units/range:** standard spoils 20% of each resource (30% with Looting Teams), conditional surrender 10%; unconditional surrender full spoils plus manpower cap x0.5 for 5 days. Min war duration 24h to end by peace/surrender; truce 3 days (aggressor), 24h defender cooldown; 1 nuke volley per side per war.
Daily reparation after a morale-break war: see economy-taxes-revenue.md ("War reparation tax").

### Auto expiry
**Exact rule** (verbatim) - **Source:** `app_core/game_ticks/war_expiry.py:9-12`
```python
import time

TASK_NAME = "war_auto_expiry"
ADVISORY_LOCK_ID = 9032
```
**Notes:** wars older than 7 days end as white peace; scheduled :50 hourly.

### Citizen army
**Exact rule** (verbatim) - **Source:** `wars/supply.py:26-40`
```python
CITIZEN_ARMY_MIN_PCT = 0.04
CITIZEN_ARMY_MAX_PCT = 0.25
CITIZEN_ARMY_SOFTNESS = 60.0
CITIZEN_ARMY_PROVINCE_WEIGHT = 2.0
# Per-battle variance on the citizen army's damage (still clamped to MAX).
CITIZEN_ARMY_VARIANCE = (0.85, 1.15)


def citizen_army_pct(population: int, provinces: int) -> float:
    """Deterministic share of the attacking force the citizen army destroys."""
    pop_m = max(0.0, float(population or 0)) / 1_000_000.0
    score = pop_m + CITIZEN_ARMY_PROVINCE_WEIGHT * max(0, int(provinces or 0))
    span = CITIZEN_ARMY_MAX_PCT - CITIZEN_ARMY_MIN_PCT
    pct = CITIZEN_ARMY_MIN_PCT + span * (1.0 - math.exp(-score / CITIZEN_ARMY_SOFTNESS))
    return min(CITIZEN_ARMY_MAX_PCT, pct)
```
**Units/range:** applies when the defender fields no combat-capable units.

### Civilian deaths and bomber ground strike
**Exact rule** (verbatim) - **Source:** `wars/aftermath.py:20-30`
```python
CIVILIAN_DEATHS = {
    "ground": {1: 0.01, 2: 0.02, 3: 0.03},
    "bombers": {1: 0.02, 2: 0.04, 3: 0.06},
}

# Share of the defender's soldiers/tanks destroyed by a won bomber attack,
# capped at BOMBER_KILL_CAP units per surviving bomber.
BOMBER_GROUND_LOSS = {1: 0.05, 2: 0.10, 3: 0.15}
BOMBER_KILL_CAP = {"soldiers": 25, "tanks": 2}

NUKE_FALLOUT_DEATHS = 0.01  # whole target nation
```
**Exact rule** (verbatim) - **Source:** `wars/aftermath.py:37-67`
```python
def civilian_death_pct(domain, attacker_units, win_condition) -> float:
    """Share of the attacked province's population killed by a WON attack."""
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
```
## Not found / open questions
- Peace-offer terms, ally joining (wars/routes.py:380-590, 1956-2097) not read.
- Strategic airstrike, drone strike, cruise missile numbers (wars/routes.py:2557-3200) not read.
