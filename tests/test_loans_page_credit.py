"""Loans page credit/capacity block + /loans/quote against a real (local,
throwaway) Postgres. Creates one temporary user and removes it afterwards."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from database import get_db_connection

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres",
)


@pytest.fixture
def borrower(client):
    name = f"loancred_{uuid.uuid4().hex[:8]}"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO users (username, email, date, hash, auth_type) VALUES (%s,%s,%s,'','normal') RETURNING id",
            (name, f"{name}@example.test", "2026-09-27"),
        )
        uid = db.fetchone()[0]
        db.execute("INSERT INTO stats (id, location, gold) VALUES (%s,'Grassland',0)", (uid,))
        db.execute("INSERT INTO provinces (userId, provinceName, population) VALUES (%s, 'P', 1000000)", (uid,))
        conn.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    try:
        yield uid
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            for sql in ("DELETE FROM user_loans WHERE user_id=%s", "DELETE FROM provinces WHERE userId=%s",
                        "DELETE FROM news WHERE destination_id=%s", "DELETE FROM referral_active_days WHERE referred_user_id=%s",
                        "DELETE FROM stats WHERE id=%s",
                        "DELETE FROM users WHERE id=%s"):
                db.execute(sql, (uid,))
            conn.commit()


def test_quote_endpoint_uses_server_cap(client, borrower):
    from app_core.loans.services import compute_loan_cap, loan_quote

    with get_db_connection() as conn:
        cap = compute_loan_cap(conn.cursor(), borrower)
    assert cap > 0
    amount = int(cap * 0.9)
    data = client.get(f"/loans/quote?amount={amount}").get_json()
    assert data == {**loan_quote(amount, cap)}
    assert data["over_threshold"] is True and data["valid"] is True


def test_page_renders_credit_block_and_active_loan_indicator(client, borrower):
    body = client.get("/loans").get_data(as_text=True)
    assert "Credit &amp; Capacity" in body and "loanCalcAmount" in body
    assert "Current loan vs. capacity" not in body

    # A loan taken 30 days ago and still open = in default, lowers the score.
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "INSERT INTO user_loans (user_id, principal, balance, interest_rate, taken_at, cap_at_take) "
            "VALUES (%s, 1000000, 1100000, 0, %s, 5000000)",
            (borrower, datetime.now(timezone.utc) - timedelta(days=30)),
        )
        conn.commit()
    body = client.get("/loans").get_data(as_text=True)
    assert "Current loan vs. capacity" in body
    assert "You could borrow after repaying" in body
    assert "in default" in body
