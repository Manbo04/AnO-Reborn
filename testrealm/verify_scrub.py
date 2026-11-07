#!/usr/bin/env python3
"""Fail if a real-looking email, token or password hash is left in the test database.

    TEST_DATABASE_URL=postgresql://.../ano_test python testrealm/verify_scrub.py

Scans every text/varchar column in the public schema for email-shaped values (anything that is
not @test.invalid) and checks the users table for leftovers. Read-only.
"""
from __future__ import annotations

import os
import re
import sys

EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
OK_DOMAIN = "@test.invalid"


def main() -> int:
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("Set TEST_DATABASE_URL (the test copy).")
        return 2
    from urllib.parse import urlparse

    if not re.search(r"test", urlparse(dsn).path.lstrip("/"), re.I):
        print("Refusing: database name must contain 'test'.")
        return 2
    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    bad = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND data_type IN ('text','character varying') "
            "AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname='public')"
        )
        cols = cur.fetchall()
        for table, col in cols:
            cur.execute(
                f'SELECT count(*) FROM "{table}" WHERE "{col}" ~ %s AND "{col}" NOT LIKE %s',
                (EMAIL, "%" + OK_DOMAIN + "%"),
            )
            n = cur.fetchone()[0]
            if n:
                bad.append(f"{table}.{col}: {n} email-shaped values")
        cur.execute("SELECT count(*) FROM users WHERE verification_token IS NOT NULL OR recovery_key IS NOT NULL "
                    "OR discord_id IS NOT NULL OR totp_secret_encrypted IS NOT NULL OR totp_enabled")
        n = cur.fetchone()[0]
        if n:
            bad.append(f"users: {n} rows still carry token, recovery key, Discord id or 2FA")
    if bad:
        print("SCRUB INCOMPLETE:")
        print("\n".join(" - " + b for b in bad))
        return 1
    print(f"Scrub verified over {len(cols)} text columns: no real emails, tokens or 2FA left.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
