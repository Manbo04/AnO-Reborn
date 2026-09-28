"""Direct (nation-to-nation) trade audit, 2026-09-27 (Mohammad's 09-19 500).

Real-DB tests through the Flask test client:
- accepting a sell offer delivers the goods from escrow and does not take
  them from the seller a second time;
- bad input that used to 500 (nonexistent nation, values past the INTEGER
  columns, non-numeric trade id) now returns a 4xx and leaves no trade and
  no escrow behind;
- resetting a nation refunds the escrow of trades other nations offered it.
"""
import uuid

import bcrypt
import pytest

from database import get_db_connection

PW = bcrypt.hashpw(b"x-test-pw", bcrypt.gensalt()).decode()


def _mk_user(db, gold=0):
    name = f"dtrade_{uuid.uuid4().hex[:10]}"
    db.execute(
        "INSERT INTO users (username, email, date, hash, auth_type) "
        "VALUES (%s, %s, '2026-09-27', %s, 'normal') RETURNING id",
        (name, f"{name}@example.com", PW),
    )
    uid = db.fetchone()[0]
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s, 'Tundra', %s)", (uid, gold)
    )
    return uid


def _set_res(db, uid, name, qty):
    db.execute(
        "INSERT INTO user_economy (user_id, resource_id, quantity) "
        "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name=%s "
        "ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity=EXCLUDED.quantity",
        (uid, qty, name),
    )


def _res(uid, name):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT COALESCE(ue.quantity,0) FROM resource_dictionary rd "
            "LEFT JOIN user_economy ue ON ue.resource_id=rd.resource_id AND ue.user_id=%s "
            "WHERE rd.name=%s",
            (uid, name),
        )
        return db.fetchone()[0]


def _gold(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        row = db.fetchone()
        return row[0] if row else None


def _trades(uid):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT offer_id, type, offerer, offeree, amount, price FROM trades "
            "WHERE offerer=%s OR offeree=%s",
            (uid, uid),
        )
        return db.fetchall()


@pytest.fixture
def nations():
    with get_db_connection() as conn:
        db = conn.cursor()
        seller = _mk_user(db, gold=0)
        buyer = _mk_user(db, gold=1_000_000)
        _set_res(db, seller, "lumber", 500)
        _set_res(db, buyer, "lumber", 0)
        conn.commit()
    yield seller, buyer
    with get_db_connection() as conn:
        db = conn.cursor()
        ids = (seller, buyer)
        db.execute("DELETE FROM trades WHERE offerer = ANY(%s) OR offeree = ANY(%s)", (list(ids), list(ids)))
        db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (list(ids),))
        db.execute("DELETE FROM stats WHERE id = ANY(%s)", (list(ids),))
        # Requests through the test client log activity rows keyed on users.
        db.execute("DELETE FROM referral_active_days WHERE referred_user_id = ANY(%s)", (list(ids),))
        db.execute("DELETE FROM news WHERE destination_id = ANY(%s)", (list(ids),))
        db.execute("DELETE FROM users WHERE id = ANY(%s)", (list(ids),))
        conn.commit()


def _client(uid):
    from app import app

    app.config["WTF_CSRF_ENABLED"] = False
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return client


def test_accept_sell_offer_takes_goods_from_escrow_only(nations):
    seller, buyer = nations
    c = _client(seller)
    r = c.post(
        f"/post_trade_offer/sell/{buyer}",
        data={"resource": "lumber", "amount": "100", "price": "10"},
    )
    assert r.status_code == 302, r.data[:300]
    assert _res(seller, "lumber") == 400  # 100 escrowed
    (offer_id, *_rest) = _trades(seller)[0]

    c = _client(buyer)
    r = c.post(f"/accept_trade/{offer_id}")
    assert r.status_code == 302, r.data[:300]

    assert _res(buyer, "lumber") == 100
    # Before the fix the seller lost another 100 here (300 left).
    assert _res(seller, "lumber") == 400
    assert _gold(seller) == 1000
    assert _trades(seller) == []


@pytest.mark.parametrize(
    "path_target,data",
    [
        ("nonexistent", {"resource": "lumber", "amount": "10", "price": "10"}),
        ("buyer", {"resource": "lumber", "amount": "3000000000", "price": "1"}),
        ("buyer", {"resource": "lumber", "amount": "1", "price": "3000000000"}),
        ("huge", {"resource": "lumber", "amount": "10", "price": "10"}),
        ("self", {"resource": "lumber", "amount": "10", "price": "10"}),
        ("buyer", {"resource": "lumber", "amount": "0", "price": "10"}),
        ("buyer", {"resource": "lumber", "amount": "-5", "price": "10"}),
        ("buyer", {"resource": "notaresource", "amount": "5", "price": "10"}),
    ],
)
def test_bad_direct_offers_are_4xx_and_leave_nothing(nations, path_target, data):
    seller, buyer = nations
    for offer_type in ("sell", "buy"):
        who = seller if offer_type == "sell" else buyer
        other = buyer if who == seller else seller
        target = {
            "nonexistent": "2000000000",
            "huge": "99999999999",
            "self": str(who),
            "buyer": str(other),
        }[path_target]
        before_gold, before_lumber = _gold(who), _res(who, "lumber")
        r = _client(who).post(f"/post_trade_offer/{offer_type}/{target}", data=data)
        assert 400 <= r.status_code < 500, (offer_type, data, r.status_code)
        assert _trades(who) == []
        assert _gold(who) == before_gold
        assert _res(who, "lumber") == before_lumber


@pytest.mark.parametrize("trade_id", ["abc", "99999999999", "2000000000"])
def test_accept_bad_trade_id_is_4xx(nations, trade_id):
    _, buyer = nations
    r = _client(buyer).post(f"/accept_trade/{trade_id}")
    assert 400 <= r.status_code < 500, r.status_code


def test_refund_trades_offered_to_returns_escrow(nations):
    from app_core.market.repositories import refund_trades_offered_to

    seller, buyer = nations
    # seller offers goods to buyer; buyer offers gold to seller... then the
    # *buyer* nation is reset: seller's goods escrow must come back.
    r = _client(seller).post(
        f"/post_trade_offer/sell/{buyer}",
        data={"resource": "lumber", "amount": "50", "price": "3"},
    )
    assert r.status_code == 302
    assert _res(seller, "lumber") == 450
    with get_db_connection() as conn:
        db = conn.cursor()
        refund_trades_offered_to(db, buyer)
        conn.commit()
    assert _res(seller, "lumber") == 500
    assert _trades(seller) == []
