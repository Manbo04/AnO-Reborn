"""Hourly military upkeep, shared by the global tick and the revenue page.

The revenue page used to copy the tick's query and missed Iron Dome gasoline.
Both now read the rows from here.
"""

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


def dome_upkeep_gasoline():
    from app_core.military.iron_dome import DOME_UPKEEP_GASOLINE

    return DOME_UPKEEP_GASOLINE


def military_upkeep_rows(cursor, user_id=None):
    """Rows of (user_id, resource_id, resource, required_amount); all users when user_id is None."""
    cursor.execute(_UPKEEP_SQL, {"uid": user_id, "dome_gas": dome_upkeep_gasoline()})
    return cursor.fetchall()
