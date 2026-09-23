"""Regression test for the cross-user session leak in /statistics and /rankings.

Both routes used cache_response(public=True), sharing ONE cache slot across
every visitor. The rendered page extends layout.html, which bakes
session-specific nav chrome (own-country link, admin-menu visibility)
directly into the HTML at render time -- whoever populated the cache slot
had their own identity/admin status served to every other visitor for the
cache window. Reported by real players in Discord ("got randomly sent to
your acc", "got sent to lamlor acc randomly", both with no login in
between) and flagged as a known issue in docs/SESSION_LOG.md's 2026-07-04
session notes, but left unfixed for two months. See commit fixing this
(statistics.py: removed public=True from both cache_response calls).
"""

import re
import uuid

import bcrypt
import pytest

from database import get_db_connection

TEST_PASSWORD = bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt()).decode()


def _own_country_link(html: str) -> str | None:
    m = re.search(r'href="/country/id=(\d+)"', html)
    return m.group(1) if m else None


def _create_user(db, suffix):
    username = f"cacheleak_{suffix}_{uuid.uuid4().hex[:8]}"
    db.execute(
        """
        INSERT INTO users (username, email, date, hash, auth_type)
        VALUES (%s, %s, '2026-09-23', %s, 'normal')
        RETURNING id
        """,
        (username, f"{username}@example.com", TEST_PASSWORD),
    )
    user_id = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', 0)",
        (user_id,),
    )
    return user_id


@pytest.fixture
def two_users():
    with get_db_connection() as conn:
        db = conn.cursor()
        first_id = _create_user(db, "first")
        second_id = _create_user(db, "second")
        conn.commit()

    yield first_id, second_id

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM stats WHERE id IN (%s, %s)", (first_id, second_id))
        db.execute("DELETE FROM users WHERE id IN (%s, %s)", (first_id, second_id))
        conn.commit()


@pytest.mark.parametrize("path", ["/rankings", "/statistics"])
def test_rankings_and_statistics_do_not_leak_across_users(client, path, two_users):
    """A second, unrelated user hitting a just-cached page must see their
    own identity in the nav, never the first user's. Uses two freshly
    created real users (not hardcoded ids) so this passes against any
    database, not just one seeded with specific production-like rows."""
    first_user_id, second_user_id = two_users

    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = first_user_id
    first_resp = client.get(path)
    assert first_resp.status_code == 200
    first_html = first_resp.get_data(as_text=True)

    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = second_user_id
    second_resp = client.get(path)
    assert second_resp.status_code == 200
    second_html = second_resp.get_data(as_text=True)

    first_link = _own_country_link(first_html)
    second_link = _own_country_link(second_html)

    assert first_link == str(first_user_id)
    assert second_link == str(second_user_id), (
        f"cross-user cache leak: user {second_user_id} was served user "
        f"{first_user_id}'s own-country nav link ({second_link!r})"
    )
