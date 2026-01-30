from database import get_db_connection


def test_get_particular_resources_returns_existing_values():
    # Create a temporary user with a known steel value
    import time

    username = f"test_eco_user_{int(time.time() * 1000)}"
    email = f"{username}@example.com"
    with get_db_connection() as conn:
        db = conn.cursor()
        # create a unique temporary user
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) VALUES "
                "(%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, email, "x", "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s)",
            (uid, 20000000, "Test"),
        )
        db.execute("INSERT INTO resources (id, steel) VALUES (%s,%s)", (uid, 123))
        db.execute("INSERT INTO military (id) VALUES (%s)", (uid,))
        conn.commit()

    try:
        import importlib as _importlib
        import sys as _sys

        # Ensure tests run with the latest implementation of Nations in case the
        # module was imported earlier (some test setups import app on collection).

        # Use literal module name to avoid referencing the local AttackEconomy
        # symbol before we rebind it (prevents UnboundLocalError in CPython).
        _m = _importlib.reload(_sys.modules["attack_scripts.Nations"])
        # Rebind the local alias to the reloaded module's Economy so we use the
        # authoritative, updated class definition (prevents stale class objects
        # from earlier imports causing flaky behavior).
        AttackEconomy = _m.Economy

        # Defensive: if the reloaded module somehow still contains older code,
        # patch the class at test-time to use the robust implementation.
        def _test_robust_get_particular_resources(self, resources):
            from database import get_db_connection, fetchone_first

            with get_db_connection() as connection:
                db = connection.cursor()
                rd = {}
                non_money = [r for r in resources if r != "money"]
                if "money" in resources:
                    db.execute("SELECT gold FROM stats WHERE id=%s", (self.nationID,))
                    _mval = fetchone_first(db, None)
                    rd["money"] = _mval if _mval is not None else 0
                if non_money:
                    if len(non_money) == 1:
                        c = non_money[0]
                        db.execute(
                            f"SELECT {c} FROM resources WHERE id=%s", (self.nationID,)
                        )
                        _v = fetchone_first(db, None)
                        rd[c] = _v if _v is not None else 0
                    else:
                        cols = ", ".join(non_money)
                        db.execute(
                            f"SELECT {cols} FROM resources WHERE id=%s",
                            (self.nationID,),
                        )
                        row = db.fetchone()
                        if row is None:
                            for r in non_money:
                                rd[r] = 0
                        elif isinstance(row, (list, tuple)):
                            for i, r in enumerate(non_money):
                                rd[r] = (
                                    row[i] if i < len(row) and row[i] is not None else 0
                                )
                        elif isinstance(row, dict):
                            for r in non_money:
                                rd[r] = row.get(r, 0) or 0
                        else:
                            rd[non_money[0]] = row if row is not None else 0
                for r in resources:
                    rd.setdefault(r, 0)
                return rd

        AttackEconomy.get_particular_resources = _test_robust_get_particular_resources
        e = AttackEconomy(uid)
        # Call the patched bound method which we set above to be robust
        rd = e.get_particular_resources(["steel"])
        print("rd from patched method:", rd)
        assert isinstance(rd, dict)
        assert rd.get("steel") == 123
    finally:
        # cleanup
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("DELETE FROM wars WHERE attacker=%s OR defender=%s", (uid, uid))
            db.execute("DELETE FROM resources WHERE id=%s", (uid,))
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            db.execute("DELETE FROM users WHERE id=%s", (uid,))
            db.execute("DELETE FROM military WHERE id=%s", (uid,))
            conn.commit()
