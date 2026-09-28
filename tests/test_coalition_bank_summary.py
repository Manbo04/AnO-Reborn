"""Discord /bank-summary (Kurai, #suggestions 2026-09-26).

Pure aggregation + embed tests run anywhere; the endpoint tests need a
throwaway local Postgres (run with `env -u DATABASE_PUBLIC_URL
DATABASE_URL=<local>`). Every row the DB tests create is removed by the
`coalition` fixture's teardown (users cascade their own rows).
"""

import os
import uuid

import pytest

from bot_api import aggregate_bank_summary

BOT_SECRET = "pytest-bank-summary-secret"


# --------------------------------------------------------------- pure

@pytest.mark.no_server
def test_aggregate_splits_manual_trade_and_tax():
    rows = [
        (7, "Alpha", "manual", "deposit", "money", 100),
        (7, "Alpha", "manual", "deposit", "steel", 20),
        (7, "Alpha", "manual", "withdraw", "money", 30),
        (7, "Alpha", "tax", "deposit", "tax", 55),
        (7, "Alpha", "trade", "deposit", "oil", 400),
        (7, "Alpha", "trade", "withdraw", "money", 9000),
        (8, "Beta", "tax", "deposit", "tax", 70),
    ]
    out = aggregate_bank_summary(rows, {7: 2})
    assert [m["username"] for m in out] == ["Alpha", "Beta"]
    a, b = out
    assert a["deposits"] == {"money": 100, "steel": 20}
    assert a["withdrawals"] == {"money": 30}
    assert a["tax"] == 55
    assert a["trades"] == 2
    assert a["trade_gave"] == {"oil": 400}
    assert a["trade_got"] == {"money": 9000}
    assert b["tax"] == 70 and b["deposits"] == {} and b["trades"] == 0


@pytest.mark.no_server
def test_aggregate_sums_duplicate_groups_and_handles_deleted_user():
    rows = [
        (9, None, "manual", "deposit", "money", 5),
        (9, None, "manual", "deposit", "money", 6),
    ]
    out = aggregate_bank_summary(rows, {})
    assert out[0]["deposits"] == {"money": 11}
    assert out[0]["username"] == "Nation #9"


@pytest.mark.no_server
def test_embed_is_readable_and_within_discord_limits():
    from discord_bot.embeds import build_bank_summary_embed

    members = [
        {
            "user_id": i, "username": f"member{i}",
            "deposits": {"money": 1_000_000 + i, "steel": 5000},
            "withdrawals": {"oil": 10},
            "tax": 12_345, "trades": 1,
            "trade_gave": {"coal": 50}, "trade_got": {"money": 999},
        }
        for i in range(40)
    ]
    embed = build_bank_summary_embed(
        {"coalition_id": 3, "coalition_name": "Test", "hours": 48, "members": members, "total_tax": 5}
    )
    assert len(embed.fields) <= 25
    assert len(embed) <= 6000
    assert "last 2 days" in embed.description
    assert "Deposited" in embed.fields[0].value and "Tax paid" in embed.fields[0].value
    assert embed.fields[-1].name == "…and more"

    empty = build_bank_summary_embed({"coalition_id": 3, "hours": 24, "members": []})
    assert "No deposits" in empty.description


# ------------------------------------------------------------ endpoint

needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
    reason="Requires Postgres",
)

if os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL"):
    from test_coalition_qol_wishlist import coalition  # noqa: F401  (fixture)


def _link_discord(uid):
    from database import get_db_connection

    did = str(10**17 + int(uuid.uuid4().int % 10**12))
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("UPDATE users SET discord_id=%s WHERE id=%s", (did, uid))
        conn.commit()
    return did


def _get(client, did, hours="24"):
    return client.get(
        f"/api/bot/coalition_bank_summary?hours={hours}",
        headers={"X-Bot-Secret": BOT_SECRET, "X-Discord-User-Id": did},
    )


@needs_db
def test_endpoint_permissions(client, coalition, monkeypatch):
    monkeypatch.setenv("BOT_API_SECRET", BOT_SECRET)
    c = coalition
    member_did = _link_discord(c["member"])
    banker_did = _link_discord(c["banker"])
    deputy_did = _link_discord(c["deputy"])

    r = _get(client, member_did)
    assert r.status_code == 403
    assert _get(client, "123456789").status_code == 404  # not linked
    assert client.get(
        "/api/bot/coalition_bank_summary", headers={"X-Discord-User-Id": banker_did}
    ).status_code == 403  # no bot secret
    assert _get(client, banker_did, hours="0").status_code == 400
    assert _get(client, banker_did, hours="abc").status_code == 400

    for did in (banker_did, deputy_did):
        r = _get(client, did)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["coalition_id"] == c["col_id"]


@needs_db
def test_endpoint_aggregates_real_bank_activity(client, coalition, monkeypatch):
    """Drive real bank actions (deposit, one-off trade accept) and the tax log,
    then check the summary totals."""
    monkeypatch.setenv("BOT_API_SECRET", BOT_SECRET)
    from database import get_db_connection
    from app_core.coalition_bank import services as bank

    c = coalition
    col = c["col_id"]
    with get_db_connection() as conn:
        db = conn.cursor()
        # plain deposit + an old row outside the window
        db.execute(
            "INSERT INTO col_bank_transactions (coalition_id, user_id, actor_id, resource, amount, direction) "
            "VALUES (%s,%s,%s,'money',100,'deposit'), (%s,%s,%s,'tax',7,'deposit'), (%s,%s,%s,'tax',3,'deposit')",
            (col, c["member"], c["member"], col, c["member"], c["member"], col, c["member"], c["member"]),
        )
        db.execute(
            "INSERT INTO col_bank_transactions (coalition_id, user_id, actor_id, resource, amount, direction, created_at) "
            "VALUES (%s,%s,%s,'money',999999,'deposit', NOW() - INTERVAL '3 days')",
            (col, c["member"], c["member"]),
        )
        # a real one-off bank trade: member gives 50,000 money for 10 steel
        db.execute("UPDATE colBanks SET steel = 10 WHERE colId=%s", (col,))
        ok, msg = bank.propose_trade(db, c["member"], col, "money", "50000", "steel", "10", None)
        assert ok, msg
        db.execute("SELECT id FROM col_bank_trades WHERE user_id=%s", (c["member"],))
        trade_id = db.fetchone()[0]
        ok, msg, _ = bank.accept_trade(db, c["banker"], trade_id)
        assert ok, msg
        conn.commit()

    r = _get(client, _link_discord(c["leader"]))
    assert r.status_code == 200
    data = r.get_json()
    m = next(x for x in data["members"] if x["user_id"] == c["member"])
    assert m["deposits"] == {"money": 100}  # 3-day-old row excluded, trade legs not counted as deposits
    assert m["tax"] == 10
    assert m["trades"] == 1
    assert m["trade_gave"] == {"money": 50000}
    assert m["trade_got"] == {"steel": 10}
    assert data["total_tax"] == 10

    # 96h window picks up the old deposit
    m96 = next(x for x in _get(client, _link_discord(c["deputy"]), "96").get_json()["members"]
               if x["user_id"] == c["member"])
    assert m96["deposits"] == {"money": 1_000_099}
