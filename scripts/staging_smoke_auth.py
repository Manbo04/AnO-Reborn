"""Login as a real user created with bcrypt and GET main pages to check for errors.
Usage: PYTHONPATH=. venv python scripts/staging_smoke_auth.py
"""
import time
import requests
import os
from database import get_db_connection

TARGET = (
    os.environ.get("RAILWAY_SERVICE_WEB_URL")
    or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    or "https://affairsandorder.com"
)


def create_user(password="password123"):
    import bcrypt

    username = f"smoke_{int(time.time())}_auth"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, f"{username}@example.com", hashed, "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        stats_query = (
            "INSERT INTO stats (id, gold, location) "
            "VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING"
        )
        db.execute(
            stats_query,
            (uid, 10000000, ""),
        )
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
        )
        db.execute(
            "INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,)
        )
        db.execute(
            (
                "INSERT INTO provinces (id, userId, land, cityCount, productivity) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING"
            ),
            (uid, uid, 100, 1, 50),
        )
        conn.commit()
    return username, password, uid


def cleanup(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM provinces WHERE id=%s", (uid,))
        db.execute("DELETE FROM proInfra WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()


def main():
    username = password = None
    uid = None
    try:
        username, password, uid = create_user()
        print("Created auth user:", username, uid)

        s = requests.Session()
        r = s.post(
            f"{TARGET}/login",
            data={"username": username, "password": password},
            allow_redirects=True,
            timeout=10,
        )
        print("login status", r.status_code)

        pages = [
            "/",
            "/country",
            "/provinces",
            f"/province/{uid}",
            "/market",
            "/military",
            "/upgrades",
            "/news",
        ]

        for p in pages:
            try:
                # increase timeout to handle slow responses and fetch full page
                r = s.get(TARGET + p, timeout=30)
                ok = True
                if r.status_code >= 500:
                    ok = False
                if (
                    "An internal server error" in r.text
                    or "Traceback" in r.text
                    or "UndefinedError" in r.text
                ):
                    ok = False
                print(
                    p,
                    r.status_code,
                    "len",
                    len(r.text),
                    "ok" if ok else "FAIL (error content)",
                )
                if not ok:
                    print("--- response snippet start ---")
                    # print more of the response for debugging
                    print(r.text[:8000])
                    print("--- response snippet end ---")
            except Exception as e:
                print(p, "EXCEPTION", e)
                # continue to next page instead of aborting the whole run
                continue

    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        if uid:
            try:
                cleanup(uid)
                print("cleaned up")
            except Exception as e:
                print("cleanup failed:", e)


if __name__ == "__main__":
    main()
