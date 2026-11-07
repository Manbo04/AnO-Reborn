# Military upkeep

## Order of operations
Inside `global_tick` (every 10 minutes, gated to once per hour by `military_maintenance`): gate check (app_core/game_ticks/maintenance.py:540) -> `military_upkeep_rows` (maintenance.py:550) -> deduct what is available (maintenance.py:602) -> no unit is ever deleted; units whose maintenance resource is 0 become unusable in combat (units.py:13-38).

### Live upkeep rule
**What it is:** each unit type costs `maintenance_cost_amount` of ONE resource (`maintenance_cost_resource_id`) per unit per hour; each Iron Dome costs gasoline.
**Exact rule** (verbatim) - **Source:** `app_core/economy/military_upkeep.py:7-32`
```python
_UPKEEP_SQL = """
    SELECT costs.user_id, costs.resource_id, rd.name AS resource,
           SUM(costs.amount)::bigint AS required_amount
    FROM (
        SELECT um.user_id,
               ud.maintenance_cost_resource_id AS resource_id,
               um.quantity::numeric * ud.maintenance_cost_amount AS amount
        FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE um.quantity > 0
          AND ud.maintenance_cost_resource_id IS NOT NULL
          AND ud.maintenance_cost_amount > 0
          AND (%(uid)s::int IS NULL OR um.user_id = %(uid)s::int)
        UNION ALL
        -- Iron Dome upkeep (migration 0104): gasoline per dome.
        SELECT p.userid,
               (SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'),
               d.quantity::numeric * %(dome_gas)s
        FROM province_iron_domes d
        JOIN provinces p ON p.id = d.province_id
        WHERE d.quantity > 0
          AND (%(uid)s::int IS NULL OR p.userid = %(uid)s::int)
    ) costs
    JOIN resource_dictionary rd ON rd.resource_id = costs.resource_id
    GROUP BY costs.user_id, costs.resource_id, rd.name
"""
```
**Exact rule** (verbatim) - **Source:** `app_core/military/iron_dome.py:19`
```python
DOME_UPKEEP_GASOLINE = 20  # per dome per military-maintenance tick (hourly)
```
**Units/range:** DB-dynamic: `unit_dictionary.maintenance_cost_resource_id`, `maintenance_cost_amount`. Gold is NOT charged by this live path.
**Notes:** shortage handling: deducts `min(required, available)`; deficit is only recorded, nothing else happens.

### Military upkeep v2 (NOT WIRED IN)
**What it is:** a module with per-unit-per-year gold+resource costs and a start timestamp.
**Exact rule** (verbatim) - **Source:** `app_core/economy/military_upkeep_v2.py:13-34`
```python
UPKEEP_V2_START = datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc)

TICKS_PER_YEAR = 24

UPKEEP_V2 = {  # per unit, per game year
    "soldiers": {"money": 75_000, "rations": 1},
    "artillery": {"ammunition": 1, "money": 38_000_000},
    "tanks": {"gasoline": 1, "ammunition": 1, "steel": 2, "money": 45_000_000},
    "apaches": {"gasoline": 1, "ammunition": 1, "aluminium": 1, "money": 175_000_000},
    "bombers": {"gasoline": 3, "ammunition": 4, "aluminium": 4, "money": 1_200_000_000},
    "fighters": {"gasoline": 2, "ammunition": 2, "aluminium": 2, "money": 750_000_000},
    "submarines": {"uranium": 2, "ammunition": 10, "steel": 10, "money": 1_000_000_000},
    "destroyers": {"gasoline": 10, "ammunition": 5, "steel": 15, "money": 1_200_000_000},
    "cruisers": {"gasoline": 20, "ammunition": 15, "steel": 20, "money": 2_000_000_000},
    "aircraft_carriers": {
        "uranium": 10,
        "gasoline": 5,
        "ammunition": 30,
        "steel": 40,
        "money": 5_000_000_000,
    },
}
```
**Used by (grep):** `v2_active` -> `app_core/economy/military_upkeep_v2.py:37`; `v2_rows` -> `app_core/economy/military_upkeep_v2.py:58`; `UPKEEP_V2` -> `app_core/economy/military_upkeep_v2.py:42`, `app_core/economy/military_upkeep_v2.py:47`, `app_core/economy/military_upkeep_v2.py:75`
**Notes:** grep finds no caller of `v2_active`/`v2_rows` outside the module itself, and `maintenance.py` imports only `military_upkeep_rows`. STALE/DEAD: the numbers here are not charged.

## Not found / open questions
- Per-unit live upkeep amounts (DB).
