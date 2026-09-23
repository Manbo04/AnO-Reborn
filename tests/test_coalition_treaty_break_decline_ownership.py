"""Regression test for a real broken access control bug found live
2026-09-23 while auditing app_core/coalitions/ during the account
cross-contamination investigation (unrelated to that bug, found along the
way).

break_treaty() and decline_treaty() deleted the treaty row by id alone,
with no check that the treaty actually involved the caller's own
coalition -- unlike accept_treaty(), which correctly scopes its lookup to
col2_id=user_coalition. Any user holding leader/deputy_leader/
foreign_ambassador in ANY coalition could break or decline a treaty
between two entirely unrelated coalitions just by guessing/enumerating
offer_id. Fixed by requiring the treaty to have the caller's own coalition
as col1_id or col2_id before deleting.

Uses the real local ano_staging database (not mocked). Calls the real
break_treaty()/decline_treaty() functions directly inside a real Flask
request context, same style as this session's other coalitions/ fix.
"""
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


@pytest.fixture
def three_coalitions_with_foreign_treaty():
    """Coalition A (attacker's own, unrelated) + an Active treaty between
    coalitions B and C, neither of which the attacker belongs to."""
    with get_db_connection() as conn:
        db = conn.cursor()
        suffix = uuid.uuid4().hex[:8]

        def _create_user(role_suffix):
            username = f"treatytest_{role_suffix}_{suffix}"
            db.execute(
                """
                INSERT INTO users (username, email, date, hash, auth_type)
                VALUES (%s, %s, '2026-09-23', %s, 'normal')
                RETURNING id
                """,
                (username, f"{username}@example.com", TEST_PASSWORD),
            )
            return db.fetchone()[0]

        def _create_coalition(name_suffix):
            db.execute(
                """
                INSERT INTO colNames (name, type, date)
                VALUES (%s, 'coalition', '2026-09-23')
                RETURNING id
                """,
                (f"TreatyTest {name_suffix} {suffix}",),
            )
            return db.fetchone()[0]

        attacker_id = _create_user("attacker")
        col_a = _create_coalition("A")
        db.execute(
            "INSERT INTO coalitions_legacy (colid, userid, role) VALUES (%s, %s, 'leader')",
            (col_a, attacker_id),
        )

        col_b = _create_coalition("B")
        col_c = _create_coalition("C")
        db.execute(
            """
            INSERT INTO treaties (col1_id, col2_id, treaty_name, treaty_description, status)
            VALUES (%s, %s, 'Foreign Pact', 'unrelated to attacker', 'Active')
            RETURNING id
            """,
            (col_b, col_c),
        )
        treaty_id = db.fetchone()[0]
        conn.commit()

    yield {
        "attacker_id": attacker_id,
        "col_a": col_a,
        "col_b": col_b,
        "col_c": col_c,
        "treaty_id": treaty_id,
    }

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM treaties WHERE id = %s", (treaty_id,))
        db.execute("DELETE FROM coalitions_legacy WHERE colid = %s", (col_a,))
        db.execute("DELETE FROM colNames WHERE id IN (%s, %s, %s)", (col_a, col_b, col_c))
        db.execute("DELETE FROM users WHERE id = %s", (attacker_id,))
        conn.commit()


def _call_as(app, user_id, path, fn, *args):
    with app.test_request_context(path, method="POST"):
        from flask import session

        session["user_id"] = user_id
        return fn(*args)


def test_break_treaty_rejects_unrelated_coalition(three_coalitions_with_foreign_treaty):
    from app import app
    from app_core.coalitions.routes import break_treaty

    f = three_coalitions_with_foreign_treaty
    _call_as(app, f["attacker_id"], f"/break_treaty/{f['treaty_id']}", break_treaty, f["treaty_id"])

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id FROM treaties WHERE id = %s", (f["treaty_id"],))
        assert db.fetchone() is not None, (
            "a leader of an unrelated coalition was able to break a treaty "
            "between two other coalitions they have no part in"
        )


def test_decline_treaty_rejects_unrelated_coalition(three_coalitions_with_foreign_treaty):
    from app import app
    from app_core.coalitions.routes import decline_treaty

    f = three_coalitions_with_foreign_treaty
    _call_as(app, f["attacker_id"], f"/decline_treaty/{f['treaty_id']}", decline_treaty, f["treaty_id"])

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT id FROM treaties WHERE id = %s", (f["treaty_id"],))
        assert db.fetchone() is not None, (
            "a leader of an unrelated coalition was able to decline a "
            "treaty between two other coalitions they have no part in"
        )
