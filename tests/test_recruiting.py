from test_auth import login_session, login
from dotenv import load_dotenv
from init import BASE_URL
import time

load_dotenv()

coalition_type = "Open"


def test_recruiting_toggle_flow():
    # Unique name to avoid collisions
    coalition_name = f"test_recruiting_{int(time.time())}"
    coalition_desc = "Testing recruiting flow"

    # Create coalition with recruiting ON
    data = {
        "type": coalition_type,
        "name": coalition_name,
        "description": coalition_desc,
        "recruiting": "on",
    }

    # Ensure we're logged in (some runs execute this test in isolation)
    if not login(login_session):
        # Try to register the canonical test user then login
        from test_auth import register, register_session

        assert register(register_session)
        assert login(login_session)

    # Create coalition and capture redirect to extract coalition id
    resp = login_session.post(
        f"{BASE_URL}/establish_coalition",
        data=data,
        allow_redirects=False,
    )
    if resp.status_code in (302, 303):
        loc = resp.headers.get("Location", "")
        # Expect a redirect location that contains '/coalition/'
        assert "/coalition/" in loc, "Unexpected redirect location"
        colId = int(loc.rstrip("/").split("/")[-1])
    elif resp.status_code == 403:
        # User is already in a coalition; find it via DB lookup below
        colId = None
    else:
        raise AssertionError(f"Unexpected status code: {resp.status_code}")

    try:
        # If we were forbidden to create a new coalition,
        # find the existing one for this user
        if resp.status_code == 403:
            try:
                import psycopg2
                import os
                import credentials as creds

                conn = psycopg2.connect(
                    database=os.getenv("PG_DATABASE"),
                    user=os.getenv("PG_USER"),
                    password=os.getenv("PG_PASSWORD"),
                    host=os.getenv("PG_HOST"),
                    port=os.getenv("PG_PORT"),
                )
                db = conn.cursor()
                db.execute("SELECT id FROM users WHERE username=%s", (creds.username,))
                uid_row = db.fetchone()
                if uid_row:
                    uid = uid_row[0]
                    db.execute("SELECT colId FROM coalitions WHERE userId=%s", (uid,))
                    col_row = db.fetchone()
                    if col_row:
                        colId = col_row[0]
                db.close()
                conn.close()
            except Exception:
                # If DB lookup fails, fail early with context
                raise AssertionError(
                    "Could not determine existing coalition after 403 response"
                )

        # Check the recruitment listing shows the coalition
        r = login_session.get(f"{BASE_URL}/recruitments")
        # If we created a new coalition we expect coalition_name
        # If we used existing one, check by id
        if resp.status_code in (302, 303):
            assert coalition_name in r.text
        else:
            assert f"/coalition/{colId}" in r.text

        # Toggle recruiting off via update_col_info
        update_data = {
            "application_type": "",
            "description": coalition_desc,
            # recruiting omitted -> should be treated as off
        }
        resp2 = login_session.post(
            f"{BASE_URL}/update_col_info/{colId}",
            data=update_data,
            allow_redirects=True,
        )
        assert resp2.status_code in (200, 302, 303)

        # Confirm the coalition no longer appears on the recruiting list
        r2 = login_session.get(f"{BASE_URL}/recruitments")
        assert coalition_name not in r2.text

    finally:
        # Cleanup created rows via HTTP delete route (avoid direct DB access)
        try:
            login_session.post(f"{BASE_URL}/delete_coalition/{colId}")
        except Exception:
            pass
