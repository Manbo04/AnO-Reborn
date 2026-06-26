#!/usr/bin/env python3
"""Create legacy compatibility views over Next.js Prisma tables (idempotent).

The Flask game and Discord bot expect lowercase legacy names (``users``,
``stats``, ``provinces``, …). When production Postgres holds Prisma tables
(``User``, ``Nation``, ``Province``, …), this script creates ``CREATE OR REPLACE
VIEW`` bridges so Python code can query the live database without rewriting the
entire app.

**Critical:** ``users.id`` and all ``userid`` / ``user_id`` FKs must reference
``User.id`` (account UUID), **not** ``Nation.id``.

Usage:
    DATABASE_PUBLIC_URL='postgresql://...' python3 scripts/apply_nextjs_compat_views.py
    DATABASE_PUBLIC_URL='postgresql://...' python3 scripts/apply_nextjs_compat_views.py --dry-run

After applying views on Railway, redeploy **web**, **bot**, **celery-worker**, and **beat**.
"""


import argparse
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

load_dotenv()

# Prisma table names (case-sensitive in PostgreSQL when quoted).
PRISMA_USER = "User"
PRISMA_NATION = "Nation"
PRISMA_PROVINCE = "Province"

# Legacy view names the Python app expects.
LEGACY_USERS = "users"
LEGACY_STATS = "stats"
LEGACY_PROVINCES = "provinces"


def _connect():
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn


def _public_tables(cur) -> set:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type IN ('BASE TABLE', 'VIEW')
        """
    )
    return {r[0] for r in cur.fetchall()}


def _columns(cur, table_name: str) -> Dict[str, str]:
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def _pick(cols: Dict[str, str], candidates: Sequence[str]) -> Optional[str]:
    for name in candidates:
        if name in cols:
            return name
    return None


def _qident(name: str) -> str:
    return f'"{name}"'


def _sql_literal(expr: str) -> str:
    return expr


def _nation_join(
    user_alias: str, nation_alias: str, user_cols: Dict[str, str], nation_cols: Dict[str, str]
) -> str:
    """JOIN Nation to User — prefer Nation.userId -> User.id."""
    nation_user = _pick(
        nation_cols,
        ("userId", "user_id", "ownerId", "owner_id", "accountId", "account_id"),
    )
    user_pk = _pick(user_cols, ("id",))
    if nation_user and user_pk:
        return (
            f'LEFT JOIN {_qident(PRISMA_NATION)} {nation_alias} '
            f"ON {nation_alias}.{_qident(nation_user)} = {user_alias}.{_qident(user_pk)}"
        )
    return ""


def _build_users_view(user_cols: Dict[str, str], nation_cols: Dict[str, str]) -> str:
    u, n = "u", "n"
    user_pk = _pick(user_cols, ("id",))
    if not user_pk:
        raise RuntimeError(f'{PRISMA_USER} has no id column')

    username = _pick(
        nation_cols,
        ("name", "username", "nationName", "displayName"),
    ) or _pick(user_cols, ("username", "name", "displayName"))
    email = _pick(user_cols, ("email",))
    hash_col = _pick(user_cols, ("passwordHash", "password", "hash"))
    discord = _pick(user_cols, ("discordId", "discord_id"))
    created = _pick(user_cols, ("createdAt", "created_at", "date"))
    verified = _pick(user_cols, ("isVerified", "is_verified", "emailVerified"))
    auth_type = _pick(user_cols, ("authType", "auth_type"))
    description = _pick(user_cols, ("description", "bio"))
    flag = _pick(nation_cols, ("flag",)) or _pick(user_cols, ("flag",))
    join_num = _pick(user_cols, ("joinNumber", "join_number"))
    last_active = _pick(user_cols, ("lastActive", "last_active", "updatedAt"))

    nation_join = _nation_join(u, n, user_cols, nation_cols)

    def col_or_null(alias: str, col: Optional[str], cast: str = "") -> str:
        if not col:
            return "NULL"
        expr = f"{alias}.{_qident(col)}"
        return f"{expr}{cast}" if cast else expr

    user_name_col = _pick(user_cols, ("username", "name"))
    if username and nation_join:
        username_expr = (
            f"COALESCE({n}.{_qident(username)}, "
            f"{col_or_null(u, user_name_col or user_pk)})"
        )
    elif user_name_col:
        username_expr = col_or_null(u, user_name_col)
    else:
        username_expr = f"{u}.{_qident(user_pk)}::text"

    lines = [
        f"CREATE OR REPLACE VIEW {LEGACY_USERS} AS",
        "SELECT",
        f"  {col_or_null(u, user_pk)}::text AS id",
        f"  {username_expr} AS username",
        f"  {col_or_null(u, email)} AS email",
        f"  COALESCE({col_or_null(u, created, '::text')}, to_char(now(), 'YYYY-MM-DD')) AS date",
    ]
    if hash_col:
        lines.append(f"  {col_or_null(u, hash_col)} AS hash")
    else:
        lines.append("  ''::varchar AS hash")
    if description:
        lines.append(f"  {col_or_null(n if nation_join and description in nation_cols else u, description)} AS description")
    else:
        lines.append("  NULL::varchar AS description")
    if flag:
        lines.append(f"  {col_or_null(n if nation_join and flag in nation_cols else u, flag)} AS flag")
    else:
        lines.append("  NULL::varchar AS flag")
    lines.append("  NULL::varchar AS bg_flag")
    if discord:
        lines.append(f"  {col_or_null(u, discord)} AS discord_id")
    else:
        lines.append("  NULL::varchar AS discord_id")
    lines.append("  NULL::integer AS coalition_id")
    if verified:
        lines.append(f"  COALESCE({col_or_null(u, verified)}::boolean, false) AS is_verified")
    else:
        lines.append("  false AS is_verified")
    if auth_type:
        lines.append(f"  COALESCE({col_or_null(u, auth_type)}, 'normal') AS auth_type")
    else:
        lines.append("  'normal'::varchar AS auth_type")
    
    verification_token = _pick(user_cols, ("verificationToken", "verification_token"))
    if verification_token:
        lines.append(f"  {col_or_null(u, verification_token)} AS verification_token")
    else:
        lines.append("  NULL::varchar AS verification_token")
        
    token_created_at = _pick(user_cols, ("tokenCreatedAt", "token_created_at"))
    if token_created_at:
        lines.append(f"  {col_or_null(u, token_created_at)} AS token_created_at")
    else:
        lines.append("  NULL::timestamp AS token_created_at")
        
    lines.append("  NULL::varchar AS recovery_key")
    if join_num:
        lines.append(f"  {col_or_null(u, join_num)} AS join_number")
    if last_active:
        lines.append(f"  {col_or_null(u, last_active)} AS last_active")
    lines.append(f"FROM {_qident(PRISMA_USER)} {u}")
    if nation_join:
        lines.append(nation_join)
    return "\n".join(lines)


def _build_stats_view(user_cols: Dict[str, str], nation_cols: Dict[str, str]) -> str:
    u, n = "u", "n"
    user_pk = _pick(user_cols, ("id",))
    if not user_pk:
        raise RuntimeError(f'{PRISMA_USER} has no id column')

    location = _pick(nation_cols, ("continent", "location", "region")) or _pick(
        user_cols, ("location", "continent")
    )
    gold = _pick(nation_cols, ("gold", "treasury", "money")) or _pick(
        user_cols, ("gold",)
    )
    manpower = _pick(nation_cols, ("manpower",)) or _pick(user_cols, ("manpower",))
    default_def = _pick(nation_cols, ("defaultDefense", "default_defense")) or _pick(
        user_cols, ("defaultDefense", "default_defense")
    )

    nation_join = _nation_join(u, n, user_cols, nation_cols)

    def col_or_null(alias: str, col: Optional[str], default_sql: str) -> str:
        if not col:
            return default_sql
        return f"COALESCE({alias}.{_qident(col)}, {default_sql})"

    loc_expr = (
        col_or_null(n, location, "'Unknown'")
        if location and nation_join
        else "'Unknown'"
    )
    gold_expr = col_or_null(n if nation_join and gold in nation_cols else u, gold, "0")
    mp_expr = col_or_null(
        n if nation_join and manpower in nation_cols else u, manpower, "0"
    )
    dd_expr = (
        f"COALESCE({n}.{_qident(default_def)}, 'soldiers,tanks,artillery')"
        if default_def and nation_join and default_def in nation_cols
        else "'soldiers,tanks,artillery'"
    )

    lines = [
        f"CREATE OR REPLACE VIEW {LEGACY_STATS} AS",
        "SELECT",
        f"  {u}.{_qident(user_pk)}::text AS id",
        f"  {loc_expr}::varchar AS location",
        f"  {gold_expr}::bigint AS gold",
        f"  {mp_expr}::integer AS manpower",
        f"  {dd_expr}::text AS default_defense",
        f"FROM {_qident(PRISMA_USER)} {u}",
    ]
    if nation_join:
        lines.append(nation_join)
    return "\n".join(lines)


def _build_provinces_view(
    user_cols: Dict[str, str],
    nation_cols: Dict[str, str],
    province_cols: Dict[str, str],
) -> str:
    user_pk = _pick(user_cols, ("id",))
    prov_pk = _pick(province_cols, ("id",))
    owner = _pick(
        province_cols,
        ("userId", "user_id", "ownerId", "owner_id"),
    )
    nation_fk = _pick(province_cols, ("nationId", "nation_id"))
    nation_user = _pick(
        nation_cols,
        ("userId", "user_id", "ownerId", "owner_id", "accountId", "account_id"),
    )
    nation_pk = _pick(nation_cols, ("id",))

    if not (user_pk and prov_pk):
        raise RuntimeError(f"{PRISMA_PROVINCE} missing id column")

    # Prefer Province.userId -> User.id; else Province.nationId -> Nation.userId -> User.id
    if owner:
        userid_expr = f'p.{_qident(owner)}::text'
        from_clause = f'FROM {_qident(PRISMA_PROVINCE)} p'
        where_clause = f"  p.{_qident(owner)}::text IN (SELECT id::text FROM users)"
    elif nation_fk and nation_user and nation_pk and nation_cols:
        userid_expr = f'n.{_qident(nation_user)}::text'
        from_clause = (
            f'FROM {_qident(PRISMA_PROVINCE)} p '
            f'JOIN {_qident(PRISMA_NATION)} n ON n.{_qident(nation_pk)} = p.{_qident(nation_fk)}'
        )
        where_clause = (
            f"  n.{_qident(nation_user)}::text IN (SELECT id::text FROM users)"
        )
    else:
        raise RuntimeError(
            f"{PRISMA_PROVINCE} needs userId or nationId→Nation.userId for legacy bridge"
        )

    name = _pick(province_cols, ("provinceName", "name", "title"))
    city = _pick(province_cols, ("cityCount", "city_count", "cities"))
    land = _pick(province_cols, ("land",))
    pop = _pick(province_cols, ("population", "pop"))
    energy = _pick(province_cols, ("energy",))
    happiness = _pick(province_cols, ("happiness",))
    pollution = _pick(province_cols, ("pollution",))
    productivity = _pick(province_cols, ("productivity",))
    spending = _pick(province_cols, ("consumer_spending", "consumerSpending"))

    def c(col: Optional[str], default: str) -> str:
        if not col:
            return default
        return f'p.{_qident(col)}'

    return "\n".join(
        [
            f"CREATE OR REPLACE VIEW {LEGACY_PROVINCES} AS",
            "SELECT",
            f"  {userid_expr} AS \"userId\"",
            f"  {userid_expr} AS userid",
            f"  p.{_qident(prov_pk)} AS id",
            f"  {c(name, 'NULL::varchar')} AS \"provinceName\"",
            f"  COALESCE({c(city, '1')}, 1)::integer AS \"cityCount\"",
            f"  COALESCE({c(land, '1')}, 1)::integer AS land",
            f"  COALESCE({c(pop, '1000000')}, 1000000)::integer AS population",
            f"  COALESCE({c(energy, '0')}, 0)::integer AS energy",
            f"  COALESCE({c(happiness, '50')}, 50)::integer AS happiness",
            f"  COALESCE({c(pollution, '0')}, 0)::integer AS pollution",
            f"  COALESCE({c(productivity, '50')}, 50)::integer AS productivity",
            f"  COALESCE({c(spending, '50')}, 50)::integer AS consumer_spending",
            from_clause,
            "WHERE",
            where_clause,
        ]
    )


def _ensure_user_extra_columns(cur, dry_run: bool) -> None:
    """Add extra columns like discordId and email verification to Prisma User table when missing."""
    cols = _columns(cur, PRISMA_USER)
    
    sqls = []
    if "discordId" not in cols and "discord_id" not in cols:
        sqls.append(f'ALTER TABLE {_qident(PRISMA_USER)} ADD COLUMN IF NOT EXISTS "discordId" VARCHAR(255)')
    
    if "isVerified" not in cols and "is_verified" not in cols:
        sqls.append(f'ALTER TABLE {_qident(PRISMA_USER)} ADD COLUMN IF NOT EXISTS "isVerified" BOOLEAN DEFAULT FALSE')
        
    if "verificationToken" not in cols and "verification_token" not in cols:
        sqls.append(f'ALTER TABLE {_qident(PRISMA_USER)} ADD COLUMN IF NOT EXISTS "verificationToken" VARCHAR(255)')
        
    if "tokenCreatedAt" not in cols and "token_created_at" not in cols:
        sqls.append(f'ALTER TABLE {_qident(PRISMA_USER)} ADD COLUMN IF NOT EXISTS "tokenCreatedAt" TIMESTAMP')

    if not sqls:
        print("  OK User extra columns already present")
        return

    for sql in sqls:
        print(f"  Applying: {sql}")
        if not dry_run:
            cur.execute(sql)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = _connect()
    cur = conn.cursor()
    try:
        tables = _public_tables(cur)
        if PRISMA_USER not in tables:
            print(f"SKIP: {PRISMA_USER} table not found — not a Next.js bridged database")
            return 0

        if LEGACY_USERS in tables:
            cur.execute(
                """
                SELECT c.relkind FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = %s
                """,
                (LEGACY_USERS,),
            )
            row = cur.fetchone()
            if row and row[0] == "r":
                print(
                    "ERROR: physical table `users` exists — refuse to replace with a view."
                )
                print("       Use legacy postgres-volume or rename the table first.")
                return 1

        user_cols = _columns(cur, PRISMA_USER)
        nation_cols = _columns(cur, PRISMA_NATION) if PRISMA_NATION in tables else {}
        province_cols = (
            _columns(cur, PRISMA_PROVINCE) if PRISMA_PROVINCE in tables else {}
        )

        print("=== Next.js → legacy compatibility views ===")
        _ensure_user_extra_columns(cur, args.dry_run)

        statements: List[Tuple[str, str]] = []
        statements.append(("users", _build_users_view(user_cols, nation_cols)))
        statements.append(("stats", _build_stats_view(user_cols, nation_cols)))
        if province_cols:
            statements.append(
                (
                    "provinces",
                    _build_provinces_view(user_cols, nation_cols, province_cols),
                )
            )

        for label, sql in statements:
            print(f"\n--- {label} ---\n{sql}\n")
            if not args.dry_run:
                cur.execute(sql)
                print(f"  Applied view: {label}")

        if not args.dry_run:
            print("\nRun: python3 scripts/diagnose_database_schema.py")
            print("Redeploy web, bot, celery-worker, beat on Railway.")
        else:
            print("\n(dry-run — no changes written)")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
