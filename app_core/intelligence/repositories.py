import variables


def get_unit_quantity(db, user_id, unit_name):
    db.execute(
        """
        SELECT COALESCE(um.quantity, 0)
        FROM unit_dictionary ud
        LEFT JOIN user_military um
            ON um.unit_id = ud.unit_id AND um.user_id = %s
        WHERE ud.name = %s
        """,
        (user_id, unit_name),
    )
    row = db.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def decrease_unit_quantity(db, user_id, unit_name, amount):
    db.execute("SELECT unit_id FROM unit_dictionary WHERE name = %s", (unit_name,))
    row = db.fetchone()
    if not row:
        return
    unit_id = row[0]
    db.execute(
        """
        INSERT INTO user_military (user_id, unit_id, quantity)
        VALUES (%s, %s, 0)
        ON CONFLICT (user_id, unit_id) DO NOTHING
        """,
        (user_id, unit_id),
    )
    db.execute(
        """
        UPDATE user_military
        SET quantity = GREATEST(0, quantity - %s)
        WHERE user_id = %s AND unit_id = %s
        """,
        (amount, user_id, unit_id),
    )


def get_username(db, user_id):
    db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    row = db.fetchone()
    return row[0] if row else None


def get_spy_reports_for_user(db, cId):
    """Caller must open the cursor with cursor_factory=RealDictCursor -
    rows are consumed as dict-like objects by the service layer."""
    db.execute(
        (
            "SELECT spyinfo.*, users.username FROM spyinfo "
            "LEFT JOIN users ON spyinfo.spyee=users.id "
            "WHERE spyinfo.spyer=%s ORDER BY date ASC"
        ),
        (cId,),
    )
    return db.fetchall()


def touch_defcon(db, eId):
    """Reads defcon but never uses the result - preserved exactly as it was
    in the original spyAmount() handler (a pre-existing no-op query, not
    something introduced or removed by this migration)."""
    db.execute("SELECT defcon FROM users WHERE id=%s", (eId,))
    db.fetchone()


def get_latest_spy_operation(db, cId):
    db.execute(
        "SELECT spyee, date FROM spyinfo WHERE spyer=%s ORDER BY date DESC",
        (cId,),
    )
    return db.fetchone()


def insert_spy_operation(db, cId, eId, timestamp):
    db.execute(
        "INSERT INTO spyinfo (spyer, spyee, date) VALUES (%s, %s, %s) RETURNING id",
        (cId, eId, timestamp),
    )
    row = db.fetchone()
    return row[0] if row else None


def get_revealed_values(db, eId, object_names, spy_type):
    if spy_type == "units":
        db.execute(
            """
            SELECT ud.name, COALESCE(um.quantity, 0)
            FROM unit_dictionary ud
            LEFT JOIN user_military um
                ON um.unit_id = ud.unit_id AND um.user_id = %s
            WHERE ud.name = ANY(%s)
            """,
            (eId, object_names),
        )
    else:
        db.execute(
            """
            SELECT rd.name, COALESCE(ue.quantity, 0)
            FROM resource_dictionary rd
            LEFT JOIN user_economy ue
                ON ue.resource_id = rd.resource_id AND ue.user_id = %s
            WHERE rd.name = ANY(%s)
            """,
            (eId, object_names),
        )
    return {name: amount for name, amount in db.fetchall()}


def update_revealed_spyinfo(db, operation_id, uncovered_objects, revealed_map):
    """uncovered_objects feeds a dynamic column list, and it's derived from
    spy_type + variables.RESOURCES/UNITS at the service layer - not raw user
    input, but the whitelist check stays fused with the SQL construction
    right here (rather than split into a separate "validate" step) so the
    two can never drift apart and reopen an injection path."""
    safe_columns = set(variables.RESOURCES + variables.UNITS)
    set_clauses = []
    set_values = []
    for obj in uncovered_objects:
        if obj in safe_columns:
            set_clauses.append(f'"{obj}" = %s')
            set_values.append(int(revealed_map.get(obj, 0)))

    if not set_clauses:
        return

    spyinfo_update = f"UPDATE spyinfo SET {', '.join(set_clauses)} WHERE id=%s"
    set_values.append(operation_id)
    db.execute(spyinfo_update, tuple(set_values))
