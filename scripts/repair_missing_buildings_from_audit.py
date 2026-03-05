from database import get_db_cursor

TARGET_USER_ID = 4753


def fix_target_user(db):
    fixes = [
        ("copper_mines", 4),
        ("lumber_mills", 1),
        ("oil_refineries", 1),
        ("city_parks", 1),
        ("gas_stations", 4),
    ]

    for building_name, quantity in fixes:
        db.execute(
            """
            UPDATE user_buildings ub
            SET quantity = %s,
                last_upgraded = NOW()
            FROM building_dictionary bd
            WHERE ub.user_id = %s
              AND ub.building_id = bd.building_id
              AND bd.name = %s
            """,
            (quantity, TARGET_USER_ID, building_name),
        )


def global_repair_from_audit(db):
    db.execute(
        """
        WITH expected AS (
            SELECT
                pa.user_id,
                bd.building_id,
                GREATEST(
                    SUM(
                        CASE
                            WHEN pa.note LIKE 'buy_%' THEN pa.units
                            WHEN pa.note LIKE 'sell_%' THEN -pa.units
                            ELSE 0
                        END
                    ),
                    0
                )::int AS expected_qty
            FROM purchase_audit pa
            JOIN users u
                ON u.id = pa.user_id
            JOIN building_dictionary bd
                ON bd.name = pa.unit
            GROUP BY pa.user_id, bd.building_id
        )
        INSERT INTO user_buildings (user_id, building_id, quantity, last_upgraded)
        SELECT e.user_id, e.building_id, e.expected_qty, NOW()
        FROM expected e
        WHERE e.expected_qty > 0
        ON CONFLICT (user_id, building_id)
        DO UPDATE
           SET quantity = EXCLUDED.quantity,
               last_upgraded = NOW()
         WHERE user_buildings.quantity < EXCLUDED.quantity
        RETURNING user_id, building_id, quantity
        """
    )
    updated_rows = db.fetchall()
    return updated_rows


def main():
    with get_db_cursor() as db:
        fix_target_user(db)
        updated_rows = global_repair_from_audit(db)

        db.execute(
            """
            SELECT bd.name, ub.quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON ub.building_id = bd.building_id
            WHERE ub.user_id = %s
                            AND bd.name IN (
                                    'copper_mines',
                                    'lumber_mills',
                                    'oil_refineries',
                                    'city_parks',
                                    'gas_stations'
                            )
            ORDER BY bd.name
            """,
            (TARGET_USER_ID,),
        )
        target_rows = db.fetchall()

    print(f"GLOBAL_REPAIRS_APPLIED={len(updated_rows)}")
    print("TARGET_4753_COUNTS=")
    for name, qty in target_rows:
        print(f"{name}:{qty}")


if __name__ == "__main__":
    main()
