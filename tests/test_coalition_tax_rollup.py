"""Coalition tax log: daily-per-member rollup (default), hourly toggle, CSV of
the rollup; raw hourly rows are kept. Local throwaway Postgres only; the
`coalition` fixture removes everything it creates."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres",
)

if os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL"):
    from test_coalition_qol_wishlist import coalition, _login  # noqa: F401


def _seed(c):
    from database import get_db_connection

    rows = []
    # member: 3 payments on day A, 1 on day B; member2: 2 on day A
    for uid, ts, amt in (
        (c["member"], "2026-09-20 01:00+00", 10),
        (c["member"], "2026-09-20 02:00+00", 20),
        (c["member"], "2026-09-20 23:30+00", 30),
        (c["member"], "2026-09-21 00:30+00", 5),
        (c["member2"], "2026-09-20 05:00+00", 7),
        (c["member2"], "2026-09-20 06:00+00", 8),
    ):
        rows.append((c["col_id"], uid, uid, "tax", amt, "deposit", ts))
    rows.append((c["col_id"], c["member"], c["member"], "money", 999, "deposit", "2026-09-20 03:00+00"))
    with get_db_connection() as conn:
        db = conn.cursor()
        db.executemany(
            "INSERT INTO col_bank_transactions "
            "(coalition_id, user_id, actor_id, resource, amount, direction, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()


def test_daily_rollup_is_default_and_hourly_keeps_raw_rows(client, coalition):
    c = coalition
    _seed(c)
    _login(client, c["banker"])
    daily = client.get(f"/coalition/{c['col_id']}/bank_log?kind=tax").get_data(as_text=True)
    assert "Daily per member" in daily and "Day (UTC)" in daily
    assert "2026-09-20" in daily and "2026-09-21" in daily
    hourly = client.get(f"/coalition/{c['col_id']}/bank_log?kind=tax&view=hourly").get_data(as_text=True)
    assert "Time (UTC)" in hourly and hourly.count("2026-09-20 0") >= 4  # raw rows still listed

    csv_body = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=tax").get_data(as_text=True)
    lines = csv_body.strip().splitlines()
    assert lines[0] == "date_utc,type,member,member_id,resource,amount,payments"
    parsed = [l.split(",") for l in lines[1:]]
    got = {(p[0], int(p[3])): (int(p[5]), int(p[6])) for p in parsed}
    assert got == {
        ("2026-09-21", c["member"]): (5, 1),
        ("2026-09-20", c["member"]): (60, 3),
        ("2026-09-20", c["member2"]): (15, 2),
    }
    assert parsed[0][0] == "2026-09-21"  # newest day first

    raw = client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=tax&view=hourly").get_data(as_text=True)
    assert len(raw.strip().splitlines()) == 1 + 6


def test_rollup_respects_tax_log_permission(client, coalition):
    c = coalition
    _seed(c)
    _login(client, c["member2"])
    assert client.get(f"/coalition/{c['col_id']}/bank_log.csv?kind=tax").status_code == 403
    assert client.get(f"/coalition/{c['col_id']}/bank_log?kind=tax").status_code == 403
