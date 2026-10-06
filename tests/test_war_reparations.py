"""Truce reparations (war_reparation_tax): loser pays 20% of each resource per
day, 5% for Raze wars. The Raze rate silently never applied until 2026-10-06
(the code compared a DB row tuple to the string "Raze")."""
import time
import uuid

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users

pytestmark = pytest.mark.no_server


def _lumber(db, uid):
    db.execute(
        "SELECT COALESCE(SUM(ue.quantity), 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s AND rd.name = 'lumber'",
        (uid,),
    )
    return int(db.fetchone()[0])


@pytest.fixture
def truce():
    made = []

    def _make(war_type):
        with get_db_connection() as conn:
            db = conn.cursor()
            ids = []
            for tag in ("winner", "loser"):
                name = f"rep_{tag}_{uuid.uuid4().hex[:6]}"
                db.execute(
                    "INSERT INTO users (username, email, date, hash, auth_type) "
                    "VALUES (%s, %s, '2026-10-06', 'x', 'normal') RETURNING id",
                    (name, f"{name}@example.invalid"),
                )
                uid = db.fetchone()[0]
                db.execute("INSERT INTO stats (id, location) VALUES (%s, 'Grassland')", (uid,))
                db.execute(
                    "INSERT INTO user_economy (user_id, resource_id, quantity) "
                    "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name = 'lumber'",
                    (uid, 1000 if tag == "loser" else 0),
                )
                ids.append(uid)
            winner, loser = ids
            now = time.time()
            # defender_morale 0 -> attacker (winner) beat the defender (loser)
            db.execute(
                "INSERT INTO wars (attacker, defender, war_type, agressor_message, start_date, "
                "last_visited, peace_date, attacker_morale, defender_morale) "
                "VALUES (%s, %s, %s, 'test', %s, %s, %s, 100, 0) RETURNING id",
                (winner, loser, war_type, now, now, now),
            )
            war_id = db.fetchone()[0]
            conn.commit()
        made.append((war_id, ids))
        return winner, loser

    yield _make
    with get_db_connection() as conn:
        db = conn.cursor()
        for war_id, ids in made:
            db.execute("DELETE FROM wars WHERE id = %s", (war_id,))
            db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (ids,))
            purge_users(db, ids)
        conn.commit()


@pytest.mark.parametrize("war_type, expected_taken", [("Raze", 50), ("Sustained", 200)])
def test_reparation_rate_by_war_type(truce, war_type, expected_taken):
    from app_core.game_ticks.taxes import war_reparation_tax

    winner, loser = truce(war_type)
    war_reparation_tax()
    with get_db_connection() as conn:
        db = conn.cursor()
        assert _lumber(db, loser) == 1000 - expected_taken
        assert _lumber(db, winner) == expected_taken
