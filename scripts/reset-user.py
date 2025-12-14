import os
from dotenv import load_dotenv

load_dotenv()
import psycopg2
import sys

sys.path.append(".")
from database import get_db_cursor


def reset_user(cId):
    with get_db_cursor() as db:
        # Military
        units = [
            "soldiers",
            "artillery",
            "tanks",
            "bombers",
            "fighters",
            "apaches",
            "spies",
            "ICBMs",
            "nukes",
            "destroyers",
            "cruisers",
            "submarines",
        ]
        for unit in units:
            mil_query = f"UPDATE military SET {unit}=0" + " WHERE id=%s"
            db.execute(mil_query, (cId,))

        db.execute("UPDATE military SET manpower=100 WHERE id=%s", (cId,))
        db.execute("UPDATE military SET defcon=1 WHERE id=%s", (cId,))
        print("Reset military units, manpower, etc")

        # Player resources
        resources = [
            "oil",
            "coal",
            "uranium",
            "bauxite",
            "lead",
            "copper",
            "iron",
            "components",
            "consumer_goods",
            "gasoline",
            "ammunition",
        ]

        for resource in resources:
            rss_query = f"UPDATE resources SET {resource}=0" + " WHERE id=%s"
            db.execute(rss_query, (cId,))

        db.execute("UPDATE resources SET rations=0 WHERE id=%s", (cId,))
        db.execute("UPDATE resources SET lumber=0 WHERE id=%s", (cId,))
        db.execute("UPDATE resources SET steel=0 WHERE id=%s", (cId,))
        db.execute("UPDATE resources SET aluminium=0 WHERE id=%s", (cId,))
        db.execute("UPDATE stats SET gold=0 WHERE id=%s", (cId,))
        print("Updated players resources and money")

        # Market
        db.execute("DELETE FROM offers WHERE user_id=%s", (cId,))
        db.execute("DELETE FROM trades WHERE offerer=%s OR offeree=%s", (cId, cId))
        print("Deleted market data")

        # Provinces
        db.execute("SELECT id FROM provinces WHERE userid=%s", (cId,))
        provinces = db.fetchall()
        for id in provinces:
            id = id[0]
            print(f"Deleting province ({id}), user - {cId}")
            db.execute("DELETE FROM proInfra WHERE id=%s", (id,))
            db.execute("DELETE FROM provinces WHERE id=%s", (id,))


if __name__ == "__main__":
    # Add 100 billion gold to nation ID 20
    with get_db_cursor() as db:
        db.execute("UPDATE stats SET gold = gold + 100000000000 WHERE id = 20")
    print("Added 100 billion gold to nation ID 20")
