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


def get_counter_intel_agents(db, user_id):
    """The defender's counter-intelligence strength (unit added by
    migration 0085). 0 if the unit doesn't exist yet."""
    return get_unit_quantity(db, user_id, "counter_intel_agents")


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


def has_active_embassy(db, cId, eId):
    """True if an active embassy treaty exists between the two nations, in
    either direction. Mirrors the non_aggression check wars/routes.py uses
    to block war declarations - an embassy blocks espionage the same way."""
    db.execute(
        """
        SELECT id FROM nation_treaties
        WHERE status = 'active' AND treaty_type = 'embassy'
        AND ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
        """,
        (cId, eId, eId, cId),
    )
    return db.fetchone() is not None


def get_username(db, user_id):
    db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    row = db.fetchone()
    return row[0] if row else None


def insert_news(db, user_id, message):
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
        (user_id, message),
    )


def get_spy_reports_for_user(db, cId):
    """Caller must open the cursor with cursor_factory=RealDictCursor -
    rows are consumed as dict-like objects by the service layer."""
    db.execute(
        (
            "SELECT spyinfo.*, users.username FROM spyinfo "
            "LEFT JOIN users ON spyinfo.spyee=users.id "
            "WHERE spyinfo.spyer=%s AND NOT spyinfo.intercepted "
            "ORDER BY date ASC"
        ),
        (cId,),
    )
    return db.fetchall()




def get_last_spy_op_times(db, cId):
    """Latest operation timestamp per op type for this attacker, as
    {spy_type: date}. Rows from before migration 0085 have spy_type NULL and
    come back under the key None - the service counts those against every
    op type's cooldown."""
    db.execute(
        "SELECT spy_type, MAX(date) FROM spyinfo WHERE spyer=%s GROUP BY spy_type",
        (cId,),
    )
    return {row[0]: row[1] for row in db.fetchall() if row[1] is not None}


def insert_spy_operation(db, cId, eId, timestamp, spy_type, intercepted=False):
    db.execute(
        "INSERT INTO spyinfo (spyer, spyee, date, spy_type, intercepted) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (cId, eId, timestamp, spy_type, intercepted),
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
    revealed = {name: amount for name, amount in db.fetchall()}
    if spy_type != "units" and "money" in object_names:
        # Gold lives in stats, not user_economy; spyinfo stores it as money.
        db.execute("SELECT COALESCE(gold, 0) FROM stats WHERE id = %s", (eId,))
        row = db.fetchone()
        revealed["money"] = int(row[0]) if row else 0
    return revealed


def update_revealed_spyinfo(db, operation_id, uncovered_objects, revealed_map):
    """uncovered_objects feeds a dynamic column list, and it's derived from
    spy_type + variables.RESOURCES/UNITS at the service layer - not raw user
    input, but the whitelist check stays fused with the SQL construction
    right here (rather than split into a separate "validate" step) so the
    two can never drift apart and reopen an injection path."""
    safe_columns = set(variables.RESOURCES + variables.UNITS + ["iron_domes", "money"])
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
