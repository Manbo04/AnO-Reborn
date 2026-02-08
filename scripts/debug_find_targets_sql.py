import sys
from database import get_db_connection

try:
    print("DEBUG script start")
    # find ft_test_requester and ft_test_target
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM users WHERE username LIKE 'ft_test_%'")
        conn.commit()
        db.execute(
            "INSERT INTO users (username, email, hash, date, auth_type) "
            "VALUES (%s,%s,%s,%s,%s)",
            (
                "ft_test_requester",
                "ft_test_requester@example.com",
                "h",
                "2020-01-01",
                "normal",
            ),
        )
        db.execute(
            "INSERT INTO users (username, email, hash, date, auth_type) "
            "VALUES (%s,%s,%s,%s,%s)",
            (
                "ft_test_target",
                "ft_test_target@example.com",
                "h",
                "2020-01-01",
                "normal",
            ),
        )
        db.execute("SELECT id FROM users WHERE username=%s", ("ft_test_requester",))
        requester = db.fetchone()[0]
        db.execute("SELECT id FROM users WHERE username=%s", ("ft_test_target",))
        target = db.fetchone()[0]
        db.execute(
            "INSERT INTO provinces (userId, cityCount, land) VALUES (%s, %s, %s)",
            (target, 1, 10),
        )
        db.execute(
            "INSERT INTO military (id, soldiers, artillery) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET soldiers=%s, artillery=%s",
            (target, 100, 5, 100, 5),
        )
        conn.commit()

        print("requester", requester, "target", target)

        db.execute("SELECT COUNT(id) FROM provinces WHERE userid=%s", (requester,))
        user_provinces = db.fetchone()[0]
        print("user_provinces", user_provinces)

        # imitation of get_influence(cId) - call the function if available
        from wars.routes import get_influence

        try:
            user_influence = get_influence(requester)
        except Exception as e:
            print("get_influence failed", e)
            user_influence = 0
        print("user_influence", user_influence)

        min_provinces = max(0, user_provinces - 3)
        max_provinces = user_provinces + 1
        min_influence = max(0.0, user_influence * 0.9)
        max_influence = max(user_influence * 2.0, 100.0)
        print("province range", min_provinces, max_provinces)
        print("influence range", min_influence, max_influence)

        query = (
            "SELECT users.id, users.username, users.flag, "
            "COUNT(provinces.id) as provinces_count, "
            "COALESCE(SUM(military.soldiers * 0.02 + military.artillery * 1.6 + "
            "military.tanks * 0.8 + "
            "military.fighters * 3.5 + "
            "military.bombers * 2.5 + "
            "military.apaches * 3.2 + "
            "military.submarines * 4.5 + "
            "military.destroyers * 3 + "
            "military.cruisers * 5.5 + "
            "military.icbms * 250 + military.nukes * 500 + "
            "military.spies * 25), 0) as influence "
            "FROM users "
            "LEFT JOIN provinces ON users.id = provinces.userId "
            "LEFT JOIN military ON users.id = military.id "
            "WHERE users.id != %s "
            "GROUP BY users.id, users.username, users.flag "
            "HAVING COUNT(provinces.id) BETWEEN %s AND %s "
            "ORDER BY users.username "
            "LIMIT 50"
        )
        db.execute(query, (requester, min_provinces, max_provinces))
        rows = db.fetchall()
        print("rows count", len(rows))
        for r in rows:
            print(r)

        # check influence of target specifically
        db.execute(
            "SELECT COALESCE(SUM(military.soldiers * 0.02 + "
            "military.artillery * 1.6),0) FROM military WHERE id=%s",
            (target,),
        )
        print("target influence simple", db.fetchone()[0])

    print("done")
except Exception as e:
    print("ERROR", e)
    sys.exit(1)
