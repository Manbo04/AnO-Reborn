import os
import sys

sys.path.insert(0, '/app')
from database import get_db_cursor

starter_resources = [
    ("lumber", 120_000),
    ("iron", 50_000),
    ("coal", 50_000),
    ("rations", 350_000),
    ("steel", 15_000),
    ("components", 10_000),
    ("aluminium", 10_000),
]

with get_db_cursor() as db:
    # Set gold to 80,000,000
    db.execute("UPDATE stats SET gold = 80000000 WHERE id = 8")
    
    # Give starting resources
    for res_name, qty in starter_resources:
        db.execute(
            """
            UPDATE user_economy SET quantity = quantity + %s
            WHERE user_id = 8
              AND resource_id = (
                  SELECT resource_id FROM resource_dictionary WHERE name = %s
              )
            """,
            (qty, res_name),
        )

print("Gave User 8 starting resources.")
