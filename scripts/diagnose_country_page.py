#!/usr/bin/env python3
"""Diagnose country page SQL failures against production/staging Postgres.

Runs schema probes and replays each query used by countries.country() for a user id
(default: 16 test account). Exits non-zero on first failure.

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/diagnose_country_page.py
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/diagnose_country_page.py 27
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
    if "sslmode=disable" not in url:
        if "?" in url: url += "&sslmode=disable"
        else: url += "?sslmode=disable"
    return psycopg2.connect(url)


def probe_schema(cur) -> dict:
    checks = {}

    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
          AND column_name IN ('last_active', 'join_number')
        """
    )
    checks["users_columns"] = {r[0] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'provinces'
          AND column_name IN ('pop_children', 'pop_working', 'pop_elderly')
        """
    )
    checks["provinces_demographics"] = {r[0] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT to_regclass('public.resource_dictionary') AS rd,
               to_regclass('public.user_economy') AS ue,
               to_regclass('public.building_dictionary') AS bd,
               to_regclass('public.user_buildings') AS ub,
               to_regclass('public.tech_dictionary') AS td,
               to_regclass('public.user_tech') AS ut
        """
    )
    row = cur.fetchone()
    checks["normalized_tables"] = {
        "resource_dictionary": row[0],
        "user_economy": row[1],
        "building_dictionary": row[2],
        "user_buildings": row[3],
        "tech_dictionary": row[4],
        "user_tech": row[5],
    }

    return checks


def run_step(name: str, cur, sql: str, params: tuple) -> None:
    try:
        cur.execute(sql, params)
        cur.fetchall() if cur.description else None
        print(f"  OK  {name}")
    except Exception as exc:
        print(f"  FAIL {name}: {exc}")
        raise


def replay_country_queries(cur, user_id: int) -> None:
    print(f"\nReplaying country() queries for user_id={user_id}:\n")

    run_step(
        "core user+stats+coalition+provinces",
        cur,
        """SELECT u.username, s.location, u.description,
                  u.date, u.flag,
                  c.id AS coalition_id, cm.role,
                  c.name as colName,
                  p.total_pop, p.avg_happiness,
                  p.avg_productivity, p.province_count
           FROM users u
           INNER JOIN stats s ON u.id=s.id
           LEFT JOIN coalitions_legacy cm ON u.id=cm.userid
           LEFT JOIN colNames c ON cm.colid=c.id
           LEFT JOIN (
               SELECT userid,
                      SUM(population) AS total_pop,
                      AVG(happiness) AS avg_happiness,
                      AVG(productivity) AS avg_productivity,
                      COUNT(id) AS province_count
               FROM provinces
               WHERE userid = %s
               GROUP BY userid
           ) p ON u.id = p.userid
           WHERE u.id=%s""",
        (user_id, user_id),
    )

    run_step(
        "optional join_number + last_active",
        cur,
        "SELECT join_number, last_active FROM users WHERE id=%s",
        (user_id,),
    )

    run_step(
        "optional demographic aggregates",
        cur,
        """SELECT COALESCE(SUM(pop_children), 0),
                  COALESCE(SUM(pop_working), 0),
                  COALESCE(SUM(pop_elderly), 0)
           FROM provinces WHERE userid = %s""",
        (user_id,),
    )

    run_step(
        "policies",
        cur,
        "SELECT soldiers, education FROM policies WHERE user_id=%s",
        (user_id,),
    )

    run_step(
        "provinces list with demographics",
        cur,
        """SELECT provinceName, id, population,
                  CAST(citycount AS INTEGER) as cityCount,
                  land, happiness, productivity,
                  COALESCE(pop_children, 0) as pop_children,
                  COALESCE(pop_working, 0) as pop_working,
                  COALESCE(pop_elderly, 0) as pop_elderly
           FROM provinces WHERE userid=%s ORDER BY id ASC""",
        (user_id,),
    )

    run_step(
        "resource_dictionary + user_economy",
        cur,
        """SELECT rd.display_name, COALESCE(ue.quantity, 0) AS quantity
           FROM resource_dictionary rd
           LEFT JOIN user_economy ue
             ON ue.resource_id = rd.resource_id AND ue.user_id = %s
           ORDER BY rd.resource_id""",
        (user_id,),
    )

    run_step(
        "user_buildings + building_dictionary",
        cur,
        """SELECT bd.display_name, SUM(ub.quantity) AS quantity
           FROM user_buildings ub
           JOIN building_dictionary bd ON bd.building_id = ub.building_id
           WHERE ub.user_id = %s AND ub.quantity > 0
           GROUP BY bd.display_name
           HAVING SUM(ub.quantity) > 0""",
        (user_id,),
    )

    run_step(
        "user_tech + tech_dictionary",
        cur,
        """SELECT td.display_name
           FROM user_tech ut
           JOIN tech_dictionary td ON td.tech_id = ut.tech_id
           WHERE ut.user_id = %s AND ut.is_unlocked = TRUE""",
        (user_id,),
    )


def main() -> None:
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else TEST_USER_ID

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print("Schema probe:")
            checks = probe_schema(cur)
            print(f"  users columns: {sorted(checks['users_columns'])}")
            print(
                f"  provinces demographics: "
                f"{sorted(checks['provinces_demographics'])}"
            )
            for name, reg in checks["normalized_tables"].items():
                status = "present" if reg else "MISSING"
                print(f"  {name}: {status}")

            missing_users = {"last_active", "join_number"} - checks["users_columns"]
            missing_demo = {
                "pop_children",
                "pop_working",
                "pop_elderly",
            } - checks["provinces_demographics"]
            if missing_users:
                print(f"\nWARN: missing users columns: {sorted(missing_users)}")
                print("  Apply migrations/0011 and 0012")
            if missing_demo:
                print(f"\nWARN: missing provinces columns: {sorted(missing_demo)}")
                print("  Apply migrations/0013")

            replay_country_queries(cur, user_id)
            print("\nAll country page queries succeeded.")
    except Exception:
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
