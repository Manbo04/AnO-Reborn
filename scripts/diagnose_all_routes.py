#!/usr/bin/env python3
"""Probe production/staging schema and replay SQL for high-traffic routes.

Exits non-zero on the first failure. Use after deploy or when investigating 500s.

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/diagnose_all_routes.py
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/diagnose_all_routes.py 16
"""


import os
import sys

from dotenv import load_dotenv

load_dotenv()

TEST_USER_ID = 16


def get_connection():
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)
    return psycopg2.connect(url)


def run_step(name: str, cur, sql: str, params: tuple = ()) -> None:
    try:
        cur.execute(sql, params)
        cur.fetchone() if cur.description else None
        print(f"  OK  {name}")
    except Exception as exc:
        print(f"  FAIL {name}: {exc}")
        raise


def probe_schema(cur) -> None:
    print("=== Schema probes ===")
    checks = [
        ("users.last_active", "users", "last_active"),
        ("users.join_number", "users", "join_number"),
        ("users.discord_id", "users", "discord_id"),
        ("users.flag_data", "users", "flag_data"),
        ("provinces.pop_children", "provinces", "pop_children"),
        ("colnames.tax_rate", "colnames", "tax_rate"),
        ("colnames.flag_data", "colnames", "flag_data"),
        ("resource_dictionary", None, None),
    ]
    for label, table, col in checks:
        if table is None:
            cur.execute("SELECT to_regclass('public.resource_dictionary')")
            ok = cur.fetchone()[0] is not None
        else:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s AND column_name=%s
                """,
                (table, col),
            )
            ok = cur.fetchone() is not None
        print(f"  {'OK' if ok else 'MISSING':7} {label}")


def main() -> None:
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else TEST_USER_ID
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        probe_schema(cur)
        print(f"\n=== Route SQL replay (user_id={user_id}) ===")

        run_step(
            "login policies row",
            cur,
            "SELECT 1 FROM policies WHERE user_id = %s LIMIT 1",
            (user_id,),
        )

        run_step(
            "login user lookup",
            cur,
            """
            SELECT id, username, email, description, hash, auth_type
            FROM users WHERE id = %s AND auth_type = 'normal'
            """,
            (user_id,),
        )

        run_step(
            "resources layout",
            cur,
            """
            SELECT s.gold, rd.name, COALESCE(ue.quantity, 0)
            FROM stats s
            CROSS JOIN resource_dictionary rd
            LEFT JOIN user_economy ue
              ON ue.resource_id = rd.resource_id AND ue.user_id = s.id
            WHERE s.id = %s
            LIMIT 5
            """,
            (user_id,),
        )

        run_step(
            "provinces list",
            cur,
            """
            SELECT CAST(citycount AS INTEGER), provinceName, id
            FROM provinces WHERE userId=%s ORDER BY id ASC LIMIT 3
            """,
            (user_id,),
        )

        cur.execute("SELECT id FROM provinces WHERE userId=%s LIMIT 1", (user_id,))
        prow = cur.fetchone()
        if prow:
            pid = prow[0]
            run_step(
                "province detail",
                cur,
                """
                SELECT p.id, CAST(p.citycount AS INTEGER), s.location
                FROM provinces p
                LEFT JOIN stats s ON p.userId = s.id
                WHERE p.id = %s
                """,
                (pid,),
            )

        run_step(
            "countries listing",
            cur,
            """
            SELECT u.id, u.name, s.gold
            FROM users u
            JOIN stats s ON s.id = u.id
            ORDER BY s.gold DESC NULLS LAST
            LIMIT 5
            """,
        )

        members_tbl = None
        cur.execute(
            """
            SELECT CASE
                WHEN to_regclass('public.coalitions_legacy') IS NOT NULL
                    THEN 'coalitions_legacy'
                WHEN to_regclass('public.coalitions') IS NOT NULL
                    THEN 'coalitions'
                ELSE NULL
            END
            """
        )
        row = cur.fetchone()
        members_tbl = row[0] if row else None
        if members_tbl:
            run_step(
                "coalition membership",
                cur,
                f"SELECT colid FROM {members_tbl} WHERE userid=%s LIMIT 1",
                (user_id,),
            )

        run_step(
            "account user row",
            cur,
            "SELECT id, name, email FROM users WHERE id=%s",
            (user_id,),
        )

        print("\nAll probes passed.")
    except Exception:
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
