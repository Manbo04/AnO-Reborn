"""Raw SQL for currency unions (tables from migration 0083)."""


def get_membership(db, user_id):
    """(union_id, union_name, currency_name, founder_id, member_count) or None."""
    db.execute(
        """
        SELECT cu.id, cu.name, cu.currency_name, cu.founder_id,
               (SELECT COUNT(*) FROM currency_union_members m2
                 WHERE m2.union_id = cu.id)
        FROM currency_union_members m
        JOIN currency_unions cu ON cu.id = m.union_id
        WHERE m.user_id = %s
        """,
        (user_id,),
    )
    return db.fetchone()


def get_union(db, union_id):
    db.execute(
        "SELECT id, name, currency_name, founder_id, created_at "
        "FROM currency_unions WHERE id = %s",
        (union_id,),
    )
    return db.fetchone()


def union_name_taken(db, name):
    db.execute("SELECT 1 FROM currency_unions WHERE LOWER(name) = LOWER(%s)", (name,))
    return db.fetchone() is not None


def insert_union(db, name, currency_name, founder_id):
    db.execute(
        "INSERT INTO currency_unions (name, currency_name, founder_id) "
        "VALUES (%s, %s, %s) RETURNING id",
        (name, currency_name, founder_id),
    )
    return db.fetchone()[0]


def add_member(db, union_id, user_id):
    db.execute(
        "INSERT INTO currency_union_members (user_id, union_id) VALUES (%s, %s)",
        (user_id, union_id),
    )
    db.execute("DELETE FROM currency_union_applications WHERE user_id = %s", (user_id,))


def remove_member(db, user_id):
    db.execute("DELETE FROM currency_union_members WHERE user_id = %s", (user_id,))


def delete_union(db, union_id):
    db.execute("DELETE FROM currency_unions WHERE id = %s", (union_id,))


def set_founder(db, union_id, user_id):
    db.execute(
        "UPDATE currency_unions SET founder_id = %s WHERE id = %s", (user_id, union_id)
    )


def oldest_other_member(db, union_id, exclude_user_id):
    db.execute(
        "SELECT user_id FROM currency_union_members "
        "WHERE union_id = %s AND user_id <> %s ORDER BY joined_at, user_id LIMIT 1",
        (union_id, exclude_user_id),
    )
    row = db.fetchone()
    return row[0] if row else None


def is_member_of(db, union_id, user_id):
    db.execute(
        "SELECT 1 FROM currency_union_members WHERE union_id = %s AND user_id = %s",
        (union_id, user_id),
    )
    return db.fetchone() is not None


def add_application(db, union_id, user_id):
    db.execute(
        "INSERT INTO currency_union_applications (union_id, user_id) "
        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (union_id, user_id),
    )


def delete_application(db, union_id, user_id):
    db.execute(
        "DELETE FROM currency_union_applications WHERE union_id = %s AND user_id = %s "
        "RETURNING user_id",
        (union_id, user_id),
    )
    return db.fetchone() is not None


def get_applications(db, union_id):
    db.execute(
        """
        SELECT a.user_id, u.username, a.created_at
        FROM currency_union_applications a
        JOIN users u ON u.id = a.user_id
        WHERE a.union_id = %s
        ORDER BY a.created_at
        """,
        (union_id,),
    )
    return db.fetchall()


def get_my_applications(db, user_id):
    db.execute(
        "SELECT union_id FROM currency_union_applications WHERE user_id = %s",
        (user_id,),
    )
    return {row[0] for row in db.fetchall()}


def list_unions(db):
    """Every union with member count and combined public stats, one query."""
    db.execute("""
        SELECT cu.id, cu.name, cu.currency_name, cu.founder_id, fu.username,
               COUNT(m.user_id) AS members,
               COALESCE(SUM(p.population), 0) AS population,
               COALESCE(SUM(p.provinces), 0) AS provinces
        FROM currency_unions cu
        JOIN users fu ON fu.id = cu.founder_id
        LEFT JOIN currency_union_members m ON m.union_id = cu.id
        LEFT JOIN (
            SELECT userId, SUM(population) AS population, COUNT(*) AS provinces
            FROM provinces GROUP BY userId
        ) p ON p.userId = m.user_id
        GROUP BY cu.id, fu.username
        ORDER BY members DESC, cu.created_at
        """)
    return db.fetchall()


def get_members(db, union_id):
    """(user_id, username, population, provinces, joined_at) per member."""
    db.execute(
        """
        SELECT m.user_id, u.username,
               COALESCE(SUM(p.population), 0), COUNT(p.id), m.joined_at
        FROM currency_union_members m
        JOIN users u ON u.id = m.user_id
        LEFT JOIN provinces p ON p.userId = m.user_id
        WHERE m.union_id = %s
        GROUP BY m.user_id, u.username, m.joined_at
        ORDER BY m.joined_at, m.user_id
        """,
        (union_id,),
    )
    return db.fetchall()


def same_active_union(db, user_a, user_b, min_members):
    """True if both nations are in the same union that has >= min_members."""
    db.execute(
        """
        SELECT 1
        FROM currency_union_members a
        JOIN currency_union_members b ON b.union_id = a.union_id
        WHERE a.user_id = %s AND b.user_id = %s
          AND (SELECT COUNT(*) FROM currency_union_members c
                WHERE c.union_id = a.union_id) >= %s
        """,
        (user_a, user_b, min_members),
    )
    return db.fetchone() is not None


def insert_news(db, user_id, message):
    db.execute(
        "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
        (user_id, message),
    )
