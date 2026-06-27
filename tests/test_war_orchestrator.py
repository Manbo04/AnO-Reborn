import time
import psycopg2
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

from attack_scripts.war_orchestrator import persist_fight_results


def _make_user(db, username_prefix="u"):
    # usernames are limited in length by the DB schema; keep them very short
    username = f"{username_prefix}{uuid.uuid4().hex[:4]}"
    email = f"{username}@example.test"
    password_hash = "x"  # not used by these DB-only tests

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


def test_persist_fight_results_updates_military_and_morale():
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()

    # Create two transient users and an active war between them
    uid1 = _make_user(db)
    uid2 = _make_user(db)

    # Seed military counts for both users
    db.execute(
        "UPDATE military SET soldiers=%s, tanks=%s WHERE id=%s",
        (100, 10, uid1),
    )
    db.execute(
        "UPDATE military SET soldiers=%s, tanks=%s WHERE id=%s",
        (80, 5, uid2),
    )

    # Insert an active war row with morale values
    now = int(time.time())
    db.execute(
        "INSERT INTO wars (attacker,defender,war_type,agressor_message,start_date,attacker_supplies,defender_supplies,last_visited,attacker_morale,defender_morale) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (uid1, uid2, "Test", "desc", now, 0, 0, now, 100, 100),
    )
    war_id = db.fetchone()[0]

    conn.commit()

    # Minimal winner/loser objects (persist_fight_results only needs user_id)
    class _Obj:
        def __init__(self, user_id):
            self.user_id = user_id

    winner = _Obj(uid1)
    loser = _Obj(uid2)

    # Apply casualties and expect morale to drop by 10 for win_type=2
    winner_pairs = [("soldiers", 10), ("tanks", 1)]
    loser_pairs = [("soldiers", 20), ("tanks", 2)]

    win_condition = persist_fight_results(
        winner, loser, winner_pairs, loser_pairs, "defender_morale", None, 2
    )

    # Verify returned label
    assert win_condition == "definite victory"

    # Verify military counts updated
    db.execute("SELECT soldiers, tanks FROM military WHERE id=%s", (uid1,))
    s1, t1 = db.fetchone()
    assert s1 == 90
    assert t1 == 9

    db.execute("SELECT soldiers, tanks FROM military WHERE id=%s", (uid2,))
    s2, t2 = db.fetchone()
    assert s2 == 60
    assert t2 == 3

    # Verify morale updated on the war row
    db.execute("SELECT defender_morale FROM wars WHERE id=%s", (war_id,))
    new_morale = db.fetchone()[0]
    assert new_morale == 90  # 100 - 10

    # Check the audit log entry we just inserted
    db.execute(
        "SELECT winner, loser, winner_losses, loser_losses, morale_column, morale_delta, new_morale, win_label, concluded FROM war_events WHERE war_id=%s ORDER BY id DESC LIMIT 1",
        (war_id,),
    )
    audit = db.fetchone()
    assert audit is not None
    (
        a_winner,
        a_loser,
        a_wloss,
        a_lloss,
        a_mcol,
        a_mdelta,
        a_nmorale,
        a_label,
        a_concluded,
    ) = audit
    assert a_winner == uid1
    assert a_loser == uid2
    assert "soldiers" in a_wloss and "tanks" in a_wloss
    assert "soldiers" in a_lloss and "tanks" in a_lloss
    assert a_mcol == "defender_morale"
    assert a_mdelta == 10
    assert a_nmorale == 90
    assert a_label == "definite victory"
    assert a_concluded is False

    # Cleanup
    db.execute("DELETE FROM war_events WHERE war_id=%s", (war_id,))
    db.execute("DELETE FROM wars WHERE id=%s", (war_id,))
    db.execute("DELETE FROM military WHERE id=%s", (uid1,))
    db.execute("DELETE FROM military WHERE id=%s", (uid2,))
    db.execute("DELETE FROM resources WHERE id=%s", (uid1,))
    db.execute("DELETE FROM resources WHERE id=%s", (uid2,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid1,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid2,))
    db.execute("DELETE FROM users WHERE id=%s", (uid1,))
    db.execute("DELETE FROM users WHERE id=%s", (uid2,))
    conn.commit()
    conn.close()


def test_persist_fight_results_concludes_war_when_morale_reaches_zero():
    conn = psycopg2.connect(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
    )
    db = conn.cursor()

    uid1 = _make_user(db)
    uid2 = _make_user(db)

    # Ensure loser has few morale points so win_type=2 ends the war
    db.execute(
        "INSERT INTO wars (attacker,defender,war_type,agressor_message,start_date,attacker_supplies,defender_supplies,last_visited,attacker_morale,defender_morale) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (uid1, uid2, "Test", "desc", int(time.time()), 0, 0, int(time.time()), 5, 5),
    )
    war_id = db.fetchone()[0]

    db.execute("UPDATE military SET soldiers=%s WHERE id=%s", (50, uid1))
    db.execute("UPDATE military SET soldiers=%s WHERE id=%s", (40, uid2))
    conn.commit()

    class _Obj:
        def __init__(self, user_id):
            self.user_id = user_id

    winner = _Obj(uid1)
    loser = _Obj(uid2)

    # Use minimal casualties; the important part is morale drop
    win_condition = persist_fight_results(
        winner, loser, [("soldiers", 1)], [("soldiers", 1)], "defender_morale", None, 2
    )

    assert win_condition == "definite victory"

    db.execute("SELECT peace_date FROM wars WHERE id=%s", (war_id,))
    peace_date = db.fetchone()[0]
    assert peace_date is not None

    # Verify audit log recorded conclusion
    db.execute(
        "SELECT winner, loser, morale_delta, new_morale, win_label, concluded FROM war_events WHERE war_id=%s ORDER BY id DESC LIMIT 1",
        (war_id,),
    )
    audit = db.fetchone()
    assert audit is not None
    aw, al, amd, anm, alabel, aconc = audit
    assert aw == uid1
    assert al == uid2
    assert amd == 10
    assert anm <= 0
    assert alabel == "definite victory"
    assert aconc is True

    # Cleanup
    db.execute("DELETE FROM war_events WHERE war_id=%s", (war_id,))
    db.execute("DELETE FROM wars WHERE id=%s", (war_id,))
    db.execute("DELETE FROM military WHERE id=%s", (uid1,))
    db.execute("DELETE FROM military WHERE id=%s", (uid2,))
    db.execute("DELETE FROM resources WHERE id=%s", (uid1,))
    db.execute("DELETE FROM resources WHERE id=%s", (uid2,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid1,))
    db.execute("DELETE FROM stats WHERE id=%s", (uid2,))
    db.execute("DELETE FROM users WHERE id=%s", (uid1,))
    db.execute("DELETE FROM users WHERE id=%s", (uid2,))
    conn.commit()
    conn.close()
