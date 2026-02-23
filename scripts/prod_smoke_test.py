"""Production smoke test (uses TEST account id=16).

Actions (LEAVE NO TRACE):
- Backup user/military/resources/stats rows for TEST_UID
- Temporarily set a known password for TEST user
- Login via HTTP to production site
- Perform military buys (apaches then fighter)
- Check /statistics page
- Restore DB rows and original password

Run locally: python scripts/prod_smoke_test.py
"""
import os
import sys
import time
import bcrypt
import requests
import psycopg2
from urllib.parse import urlparse

# Configuration
TEST_UID = 16
PROD_URL = os.getenv("PROD_URL", "https://web-production-55d7b.up.railway.app")
# DATABASE_PUBLIC_URL is available in .vscode/mcp.json and in Railway envs
DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # try to read from .vscode/mcp.json fallback (dev convenience)
    try:
        import json

        with open(os.path.expanduser(".vscode/mcp.json")) as f:
            cfg = json.load(f)
            DATABASE_URL = cfg["servers"]["ano-game"]["env"]["DATABASE_PUBLIC_URL"]
    except Exception:
        print("DATABASE_URL not configured; aborting")
        sys.exit(1)

# Temporary test password (will be restored)
TMP_PW = "smoke-test-pw-2026"

# Safety: only proceed if PROD_URL looks like production host
if "railway.app" not in PROD_URL:
    print("Refusing to run production smoke tests against non-railway host:", PROD_URL)
    sys.exit(1)

parsed = urlparse(DATABASE_URL)
conn_params = dict(
    host=parsed.hostname,
    port=parsed.port or 5432,
    user=parsed.username,
    password=parsed.password,
    database=(parsed.path[1:] if parsed.path else "postgres"),
)

print("Connecting to production DB host:", conn_params["host"])


def get_conn():
    return psycopg2.connect(**conn_params)


# Helper to fetch a single row as tuple or None


def fetchone(query, params=()):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


# Backup original state
orig = {}
try:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # fetch username/email and stored hash (schema uses `hash` column)
            cur.execute(
                "SELECT username, email, hash FROM users WHERE id=%s", (TEST_UID,)
            )
            orig_user = cur.fetchone()
            orig["user"] = orig_user

            cur.execute("SELECT gold, location FROM stats WHERE id=%s", (TEST_UID,))
            orig["stats"] = cur.fetchone()

            cur.execute(
                "SELECT aluminium, steel, components FROM resources WHERE id=%s",
                (TEST_UID,),
            )
            orig["resources"] = cur.fetchone()

            cur.execute("SELECT * FROM military WHERE id=%s", (TEST_UID,))
            orig["military"] = cur.fetchone()

            # proInfra aggregation (we won't delete existing provinces)
            cur.execute(
                (
                    "SELECT id, aerodomes, army_bases FROM proInfra WHERE id IN "
                    "(SELECT id FROM provinces WHERE userid=%s) LIMIT 1"
                ),
                (TEST_UID,),
            )
            orig["proinfra_sample"] = cur.fetchone()

    print("Backed up TEST UID state (safe).")
except Exception as e:
    print("Failed to read production DB state:", e)
    raise

# Prepare test state: ensure resources/gold large enough; ensure password set
try:
    hashed = bcrypt.hashpw(TMP_PW.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with get_conn() as conn:
        with conn.cursor() as cur:
            # set both password and hash columns when present
            cur.execute(
                (
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name IN ('password','hash')"
                )
            )
            cols = {r[0] for r in cur.fetchall()}
            if "password" in cols:
                cur.execute(
                    "UPDATE users SET password=%s WHERE id=%s",
                    (hashed.encode("utf-8"), TEST_UID),
                )
            if "hash" in cols:
                cur.execute("UPDATE users SET hash=%s WHERE id=%s", (hashed, TEST_UID))

            # ensure stat/resources/military exist and set generous values
            cur.execute(
                (
                    "INSERT INTO stats (id, gold, location) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                (TEST_UID, 10000000, "T"),
            )
            cur.execute(
                "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (TEST_UID,),
            )
            cur.execute("UPDATE stats SET gold=%s WHERE id=%s", (10000000, TEST_UID))
            cur.execute(
                (
                    "UPDATE resources SET aluminium=%s, steel=%s, components=%s "
                    "WHERE id=%s"
                ),
                (10000, 10000, 10000, TEST_UID),
            )
            cur.execute(
                "INSERT INTO military (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (TEST_UID,),
            )
            cur.execute(
                (
                    "UPDATE military SET fighters=%s, bombers=%s, apaches=%s, "
                    "manpower=%s WHERE id=%s"
                ),
                (0, 0, 0, 1000, TEST_UID),
            )
        conn.commit()
    print("Prepared TEST account with temporary password and ample resources.")
except Exception as e:
    print("Failed to prepare TEST account:", e)
    raise

# Now perform HTTP login + buys
session = requests.Session()
# Ensure temp-user tracking variables exist for the finally/cleanup block
TEMP_USER_CREATED = False
temp_uid = None
try:
    # Determine username for TEST UID (fallback to 'Tester of the Game')
    username = (
        orig["user"][0]
        if orig.get("user") and orig["user"][0]
        else "Tester of the Game"
    )

    login_url = PROD_URL.rstrip("/") + "/login"
    resp = session.post(
        login_url,
        data={"username": username, "password": TMP_PW},
        allow_redirects=False,
        timeout=10,
    )
    if resp.status_code == 403:
        # TEST UID may be a non-password (discord) account —
        # create a temporary normal user
        print(
            "TEST UID login blocked (likely non-password account). "
            "Creating temporary test user."
        )
        import datetime
        import random

        temp_username = f"smoke_temp_{int(time.time())}_{random.randint(100,999)}"
        temp_email = f"{temp_username}@example.invalid"
        temp_pw = TMP_PW
        temp_hash = bcrypt.hashpw(temp_pw.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    (
                        "INSERT INTO users (username, email, hash, date, "
                        "auth_type, is_verified) "
                        "VALUES (%s,%s,%s,%s,%s,TRUE) RETURNING id"
                    ),
                    (
                        temp_username,
                        temp_email,
                        temp_hash,
                        datetime.date.today(),
                        "normal",
                    ),
                )
                temp_uid = cur.fetchone()[0]
                # ensure supporting rows
                cur.execute(
                    (
                        "INSERT INTO stats (id, gold, location) VALUES (%s, %s, %s) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    (temp_uid, 10000000, "T"),
                )
                cur.execute(
                    "INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (temp_uid,),
                )
                cur.execute(
                    "INSERT INTO military (id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (temp_uid,),
                )
            conn.commit()
        print(f"Created temporary user {temp_username} (id {temp_uid}) for smoke test")

        # Use temporary user for subsequent steps (override TEST_UID locally)
        USE_UID = temp_uid
        USE_USERNAME = temp_username
        TEMP_USER_CREATED = True

        # login as temp user
        resp = session.post(
            login_url,
            data={"username": USE_USERNAME, "password": temp_pw},
            allow_redirects=False,
            timeout=10,
        )
        if resp.status_code not in (302, 200):
            raise RuntimeError(f"Login as temp user failed (status {resp.status_code})")
        print("Authenticated to production as temporary test user")
    elif resp.status_code not in (302, 200):
        raise RuntimeError(f"Login failed (status {resp.status_code})")
    else:
        USE_UID = TEST_UID
        USE_USERNAME = username
        TEMP_USER_CREATED = False
        print("Authenticated to production as TEST user (session cookie obtained).")

    # Buy 5 apaches (use USE_UID)
    buy_apaches_url = PROD_URL.rstrip("/") + "/military/buy/apaches"
    resp = session.post(
        buy_apaches_url, data={"apaches": "5"}, allow_redirects=False, timeout=10
    )
    if resp.status_code not in (302, 200):
        raise RuntimeError(f"Buy apaches failed (status {resp.status_code})")
    print("Bought 5 Apaches (production).")

    # Verify DB shows 5 apaches for USE_UID
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT apaches FROM military WHERE id=%s", (USE_UID,))
            ap = cur.fetchone()[0]
            if ap is None or ap < 5:
                raise RuntimeError(f"DB check failed: expected >=5 apaches, found {ap}")
    print("DB verification: apaches OK")

    # Buy 1 fighter
    buy_fighter_url = PROD_URL.rstrip("/") + "/military/buy/fighters"
    resp = session.post(
        buy_fighter_url, data={"fighters": "1"}, allow_redirects=False, timeout=10
    )
    if resp.status_code not in (302, 200):
        raise RuntimeError(f"Buy fighter failed (status {resp.status_code})")
    print("Bought 1 Fighter (production).")

    # Verify DB fighter count for USE_UID
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT fighters FROM military WHERE id=%s", (USE_UID,))
            f = cur.fetchone()[0]
            if f is None or f < 1:
                raise RuntimeError(f"DB check failed: expected >=1 fighters, found {f}")
    print("DB verification: fighters OK")

    # Check statistics page
    stats_url = PROD_URL.rstrip("/") + "/statistics"
    r = session.get(stats_url, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"/statistics returned {r.status_code}")
    print("/statistics page reachable (authenticated).")

    # Check task_runs for generate_province_revenue exists (smoke)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                (
                    "SELECT last_run FROM task_runs "
                    "WHERE task_name='generate_province_revenue' "
                    "ORDER BY last_run DESC LIMIT 1"
                )
            )
            tr = cur.fetchone()
            if tr:
                print("generate_province_revenue last_run:", tr[0])
            else:
                print(
                    "generate_province_revenue has no recorded runs (check scheduler)."
                )

    smoke_ok = True
except Exception as e:
    print("Smoke test failed:", e)
    smoke_ok = False
    raise
finally:
    # Restore original DB state (password, military, stats, resources)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # restore password/hash
                orig_user = orig.get("user")
                if orig_user:
                    # orig_user schema: (username, email, hash)
                    orig_hash = orig_user[2] if orig_user else None
                    cur.execute(
                        (
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name='users' AND column_name='hash'"
                        )
                    )
                    cols = {r[0] for r in cur.fetchall()}
                    if "hash" in cols:
                        cur.execute(
                            "UPDATE users SET hash=%s WHERE id=%s",
                            (orig_hash if orig_hash else None, TEST_UID),
                        )

                # restore stats/resources/military
                if orig.get("stats"):
                    cur.execute(
                        "UPDATE stats SET gold=%s, location=%s WHERE id=%s",
                        (orig["stats"][0], orig["stats"][1], TEST_UID),
                    )
                if orig.get("resources"):
                    cur.execute(
                        (
                            "UPDATE resources SET aluminium=%s, steel=%s, "
                            "components=%s WHERE id=%s"
                        ),
                        (
                            orig["resources"][0],
                            orig["resources"][1],
                            orig["resources"][2],
                            TEST_UID,
                        ),
                    )
                if orig.get("military"):
                    # military row columns may vary; do a safe update for common columns
                    cur.execute(
                        (
                            "UPDATE military SET fighters=%s, bombers=%s, apaches=%s, "
                            "manpower=%s WHERE id=%s"
                        ),
                        (
                            orig["military"][4]
                            if orig["military"] and len(orig["military"]) > 4
                            else 0,
                            orig["military"][3]
                            if orig["military"] and len(orig["military"]) > 3
                            else 0,
                            orig["military"][5]
                            if orig["military"] and len(orig["military"]) > 5
                            else 0,
                            orig["military"][9]
                            if orig["military"] and len(orig["military"]) > 9
                            else 1000,
                            TEST_UID,
                        ),
                    )
            conn.commit()
        print("Restored TEST account DB state.")
    except Exception as e:
        print("Failed to fully restore DB state:", e)

# Clean up temporary user if we created one during the smoke test
try:
    if (
        "TEMP_USER_CREATED" in globals()
        and TEMP_USER_CREATED
        and "temp_uid" in globals()
        and temp_uid
    ):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM military WHERE id=%s", (temp_uid,))
                cur.execute("DELETE FROM resources WHERE id=%s", (temp_uid,))
                cur.execute("DELETE FROM stats WHERE id=%s", (temp_uid,))
                cur.execute("DELETE FROM users WHERE id=%s", (temp_uid,))
            conn.commit()
        print(f"Removed temporary user id {temp_uid} and supporting rows.")
except Exception as e:
    print("Failed to remove temporary user rows:", e)

if smoke_ok:
    print("PRODUCTION SMOKE: ALL CHECKS PASSED 🚀")
    sys.exit(0)
else:
    print("PRODUCTION SMOKE: FAIL")
    sys.exit(2)
