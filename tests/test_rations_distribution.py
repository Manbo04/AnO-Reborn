import time
import psycopg2
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

from tasks import rations_distribution_capacity, food_stats
import variables

# enable the new mechanic for the duration of these tests
variables.FEATURE_RATIONS_DISTRIBUTION = True


def _make_user(db, username_prefix="u"):
    username = f"{username_prefix}{uuid.uuid4().hex[:4]}"
    email = f"{username}@example.test"
    password_hash = "x"

    import datetime

    db.execute(
        "INSERT INTO users (username,email,date,hash,auth_type) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (username, email, str(datetime.date.today()), password_hash, "normal"),
    )
    uid = db.fetchone()[0]

    # Ensure supporting rows exist
    db.execute(
        "INSERT INTO stats (id, location) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (uid, "T"),
    )
    db.execute("INSERT INTO military (id) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
    db.execute("INSERT INTO resources (id) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
    return uid


def test_rations_distribution_affects_food_score():
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()

    uid = _make_user(db)

    # create a single province belonging to this user
    db.execute(
        "INSERT INTO provinces (userId,population,land,citycount) VALUES (%s,%s,%s,%s) RETURNING id",
        (uid, 100000, 1, 1),
    )
    pid = db.fetchone()[0]

    # create matching proInfra row (all zero initially)
    db.execute(
        "INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT DO NOTHING",
        (pid,),
    )

    # give the user a large stockpile of rations (should be sufficient)
    db.execute("UPDATE resources SET rations=%s WHERE id=%s", (1000000, uid))
    conn.commit()

    # with no distribution buildings the capacity is zero
    cap0 = rations_distribution_capacity(uid)
    assert cap0 == 0

    score_nodist = food_stats(uid)
    # even though user has rations, his score should reflect shortage because
    # distribution capacity is zero (score < -1 means "not enough")
    assert score_nodist < -1

    # add a gas station to the province and update infra
    db.execute("UPDATE proInfra SET gas_stations=%s WHERE id=%s", (1, pid))
    conn.commit()

    cap1 = rations_distribution_capacity(uid)
    assert cap1 == variables.RATIONS_DISTRIBUTION_PER_BUILDING

    score_dist = food_stats(uid)
    assert score_dist > score_nodist

    # cleanup everything
    db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
    db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
    db.execute("DELETE FROM resources WHERE id=%s", (uid,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid,))
    db.execute("DELETE FROM military WHERE id=%s", (uid,))
    db.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()
    conn.close()


def test_province_view_shows_distribution_capacity(client):
    # Reuse the same setup logic but exercise the UI
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()

    uid = _make_user(db)
    db.execute(
        "INSERT INTO provinces (userId,population,land,citycount) VALUES (%s,%s,%s,%s) RETURNING id",
        (uid, 100000, 1, 1),
    )
    pid = db.fetchone()[0]
    db.execute("INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT DO NOTHING", (pid,))
    db.execute("UPDATE resources SET rations=%s WHERE id=%s", (1000000, uid))
    # give one distribution building so the capacity is nonzero
    db.execute("UPDATE proInfra SET gas_stations=%s WHERE id=%s", (1, pid))
    conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = uid

    resp = client.get(f"/province/{pid}")
    html = resp.data.decode()
    assert str(variables.RATIONS_DISTRIBUTION_PER_BUILDING) in html

    # cleanup
    db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
    db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
    db.execute("DELETE FROM resources WHERE id=%s", (uid,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid,))
    db.execute("DELETE FROM military WHERE id=%s", (uid,))
    db.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()
    conn.close()
