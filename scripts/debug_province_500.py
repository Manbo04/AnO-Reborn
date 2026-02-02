#!/usr/bin/env python
"""Debug province 500 error"""
from database import get_db_connection
from psycopg2.extras import RealDictCursor
import variables
import math

PROVINCE_ID = 542

with get_db_connection() as conn:
    db = conn.cursor(cursor_factory=RealDictCursor)
    db.execute(
        """
        SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
        p.pollution, p.happiness, p.productivity, p.consumer_spending,
        CAST(p.citycount AS INTEGER) as citycount,
        p.land, p.energy AS electricity,
        s.location, r.consumer_goods, r.rations, pi.*
        FROM provinces p
        LEFT JOIN stats s ON p.userId = s.id
        LEFT JOIN resources r ON p.userId = r.id
        LEFT JOIN proInfra pi ON p.id = pi.id
        WHERE p.id = %s
    """,
        (PROVINCE_ID,),
    )
    result = db.fetchone()
    result = dict(result)

    # Test the calculations that could fail
    consumer_goods = result.get("consumer_goods", 0) or 0
    rations = result.get("rations", 0) or 0
    population = result["population"]

    print("consumer_goods:", consumer_goods, type(consumer_goods))
    print("rations:", rations, type(rations))
    print("population:", population, type(population))

    max_cg = math.ceil(population / variables.CONSUMER_GOODS_PER)
    print("max_cg:", max_cg)

    rations_minus = population // variables.RATIONS_PER
    print("rations_minus:", rations_minus)
    print("enough_rations:", rations - rations_minus > 1)

    # Test energy calculations
    proinfra_columns = [
        "coal_burners",
        "oil_burners",
        "solar_fields",
        "hydro_dams",
        "nuclear_reactors",
        "gas_stations",
        "general_stores",
        "farmers_markets",
        "malls",
        "banks",
        "city_parks",
        "hospitals",
        "libraries",
        "universities",
        "monorails",
    ]
    units = {col: (result.get(col) or 0) for col in proinfra_columns}
    print("units sample:", {k: v for k, v in list(units.items())[:5]})

    consumers = variables.ENERGY_CONSUMERS
    producers = variables.ENERGY_UNITS
    new_infra = variables.NEW_INFRA

    energy_consumption = sum(units.get(c, 0) or 0 for c in consumers)
    print("energy_consumption:", energy_consumption)

    energy_production = sum(
        (units.get(p, 0) or 0) * new_infra[p]["plus"]["energy"] for p in producers
    )
    print("energy_production:", energy_production)

    print("\nAll checks passed!")
