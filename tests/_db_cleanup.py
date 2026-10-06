"""Delete test users the same way production's constraints require.

Many tables reference users(id) WITHOUT ON DELETE CASCADE (referral_active_days,
bonds, bounties, ...). Background code such as the activity ping writes some of
those rows during a test, so a bare `DELETE FROM users` in teardown fails with a
foreign-key error. This clears the referencing rows first, discovered from the
Postgres catalog so it never goes stale as tables are added.

Use only on test-created users.
"""


def _non_cascading_refs(db):
    db.execute(
        """
        SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.contype = 'f'
          AND c.confrelid = 'public.users'::regclass
          AND c.confdeltype IN ('a', 'r')   -- NO ACTION / RESTRICT
        """
    )
    return [(row[0], row[1]) for row in db.fetchall()]


def purge_users(db, user_ids):
    """Delete the given users plus rows that would block the delete."""
    ids = [int(u) for u in user_ids if u is not None]
    if not ids:
        return
    for tbl, col in _non_cascading_refs(db):
        db.execute(f'DELETE FROM {tbl} WHERE "{col}" = ANY(%s)', (ids,))
    db.execute("DELETE FROM stats WHERE id = ANY(%s)", (ids,))
    db.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))


def purge_users_where(db, where_sql, params=()):
    """purge_users() for every user matching a WHERE clause (test users only)."""
    sql = f"SELECT id FROM users WHERE {where_sql}"
    # No params -> no %-interpolation (LIKE patterns contain a literal %).
    db.execute(sql, params) if params else db.execute(sql)
    rows = db.fetchall()
    purge_users(db, [r["id"] if isinstance(r, dict) else r[0] for r in rows])
