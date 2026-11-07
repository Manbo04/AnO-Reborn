# War range and targeting

## Rule: war range is POPULATION, not influence
### Strength
**Exact rule** (verbatim) - **Source:** `wars/war_range.py:7-12`
```python
War-range strength = population / 1000. Standing units affect combat, not eligibility.
"""
from __future__ import annotations

WAR_RANGE_LOW = 0.75
WAR_RANGE_HIGH = 1.33
```
**Exact rule** (verbatim) - **Source:** `wars/war_range.py:43-50`
```python
def war_strength(population: int | float | None, military_units: dict | None = None) -> float:
    """Calculate war-range strength from population alone.

    Standing units can be bought or sold before a declaration, letting players
    manipulate matchups. Military remains decisive in combat, but not in
    target eligibility. ``military_units`` stays for caller compatibility.
    """
    return float(population or 0) / 1000.0
```
**Exact rule** (verbatim) - **Source:** `wars/war_range.py:53-59`
```python
def in_war_range(attacker_strength: float, defender_strength: float) -> bool:
    """Check if defender is within attacker's valid war range (75% to 133%)."""
    if attacker_strength <= 0:
        return defender_strength <= 0
    min_range = attacker_strength * WAR_RANGE_LOW
    max_range = attacker_strength * WAR_RANGE_HIGH
    return min_range <= defender_strength <= max_range
```
**Exact rule** (verbatim) - **Source:** `wars/war_range.py:76-83`
```python
def get_user_war_strength(db, user_id: int) -> float:
    """Fetch population-based war-range strength for a nation."""
    db.execute(
        "SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userid = %s",
        (user_id,),
    )
    row = db.fetchone()
    return war_strength(row[0] if row else 0)
```
**Units/range:** strength = total population (sum over provinces) / 1000; a target is valid when 0.75x <= target <= 1.33x of the attacker's strength. Influence and units do not enter (units explicitly excluded, war_range.py:7, 46-48).
**Used by (grep):** `get_user_war_strength` -> `wars/service.py:6`, `wars/service.py:9`, `wars/war_range.py:76`, `wars/routes.py:1844`, `wars/routes.py:1846`, `wars/routes.py:1847` (+5 more); `in_war_range` -> `wars/war_range.py:53`, `wars/routes.py:1844`, `wars/routes.py:1853`, `wars/routes.py:1971`, `wars/routes.py:1976`, `wars/routes.py:2331` (+4 more)

### Declaration checks (in order)
**Exact rule** (verbatim) - **Source:** `wars/routes.py:1764`
```python
    WAR_TYPES = ["Raze", "Sustained", "Loot"]
```
**Exact rule** (verbatim) - **Source:** `wars/routes.py:1784-1790`
```python
                "declare_war: attacker=%s defender=%s", attacker.id, defender.id
            )
            if attacker.id == defender.id:
                return error(400, "Can't declare war on yourself")
            if is_untargetable(db, defender.id):
                return error(403, UNTARGETABLE_MSG)

```
**Exact rule** (verbatim) - **Source:** `wars/routes.py:1853-1855`
```python
            if not in_war_range(attacker_strength, defender_strength):
                return error(400, format_war_range_error(attacker_strength))
            # Truce (3 days) only locks out the aggressor of the last war, so a
```
**Notes:** also: no self-war, untargetable check, vacation, non-aggression/alliance treaties, no duplicate active war, post-war lock (wars/routes.py:1796-1895; see war-combat.md for the lock lengths).

### UNIT_WEIGHTS (accounting weights, not used for eligibility)
**Exact rule** (verbatim) - **Source:** `wars/war_range.py:14-32`
```python
UNIT_WEIGHTS = {
    "soldiers": 1,
    "tanks": 40,
    "artillery": 30,
    "sam_batteries": 35,
    "fighters": 60,
    "bombers": 70,
    "apaches": 50,
    "destroyers": 120,
    "cruisers": 200,
    "submarines": 150,
    "aircraft_carriers": 250,
    "spies": 0,
    "counter_intel_agents": 0,
    "kamikaze_drones": 5,
    "cruise_missiles": 100,
    "icbms": 500,
    "nukes": 2000,
}
```
**Used by (grep):** `UNIT_WEIGHTS` -> `influence_formula.py:146`, `influence_formula.py:207`, `wars/war_range.py:36`, `wars/war_range.py:38`, `app_core/bots/war_ai.py:43`, `app_core/bots/war_ai.py:49` (+2 more)

## Not found / open questions
- `find_targets` route (wars/routes.py:2328) not read.
