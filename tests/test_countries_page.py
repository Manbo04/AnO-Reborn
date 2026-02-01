import time
import pytest
from database import get_db_connection


def create_test_user(username_prefix="ctest", provinces=1, soldiers=0, gold=0):
    username = f"{username_prefix}_{int(time.time()*1000)}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id"
            ),
            (username, f"{username}@example.com", "x", "2020-01-01", "normal"),
        )
        uid = db.fetchone()[0]
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, gold, ""),
        )
        db.execute(
            "INSERT INTO military (id, soldiers) VALUES (%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (uid, soldiers),
        )

        # Insert provinces (id == province id) using uid as base
        for i in range(provinces):
            pid = uid + i  # unique province id
            db.execute(
                (
                    "INSERT INTO provinces (id, userId, land, cityCount, productivity, "
                    "population, provinceName) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING"
                ),
                (pid, uid, 0, 1, 50, 100, f"P{pid}"),
            )
        conn.commit()
    return uid, username


def cleanup_user(uid, provinces=1):
    with get_db_connection() as conn:
        db = conn.cursor()
        # Delete provinces created
        for i in range(provinces):
            pid = uid + i
            db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
        db.execute("DELETE FROM military WHERE id=%s", (uid,))
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()

    # Invalidate any cached entries for the removed user so UI doesn't show them
    try:
        from database import invalidate_user_cache

        invalidate_user_cache(uid)
    except Exception:
        # Non-fatal for tests
        pass


def test_province_range_filtering(client):
    # simulate logged in user
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    # create user with 0 provinces and one with 2 provinces
    uid0, name0 = create_test_user("ctest0", provinces=0)
    uid2, name2 = create_test_user("ctest2", provinces=2)

    try:
        resp = client.get("/countries?province_range=1")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert name2 in data
        assert name0 not in data
    finally:
        cleanup_user(uid0, provinces=0)
        cleanup_user(uid2, provinces=2)


@pytest.mark.skip(reason="Flaky: depends on database state and pagination text format")
def test_pagination_total_count(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    uids = []
    try:
        # create 51 users so we should have at least 2 pages (page_size=50)
        for _ in range(51):
            uid, _ = create_test_user("pagetest", provinces=1)
            uids.append(uid)

        resp = client.get("/countries")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        # Check that pagination exists (at least 2 pages now)
        assert "Page 1 of" in data
    finally:
        for uid in uids:
            cleanup_user(uid, provinces=1)


@pytest.mark.skip(reason="Flaky: depends on database state and user ordering")
def test_sort_by_influence_order(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    # create two users with different soldiers (influence derived from troops)
    uid_high, name_high = create_test_user("infhigh", provinces=1, soldiers=10000)
    uid_low, name_low = create_test_user("inflow", provinces=1, soldiers=1)

    try:
        resp = client.get("/countries?sort=influence&sortway=desc")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        # first occurrence of the username should be the higher influence user
        first_high = data.find(name_high)
        first_low = data.find(name_low)
        assert first_high != -1 and first_low != -1
        assert first_high < first_low
    finally:
        cleanup_user(uid_high, provinces=1)
        cleanup_user(uid_low, provinces=1)
