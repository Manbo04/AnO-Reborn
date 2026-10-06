"""Currency market (migration 0091): holdings of other nations' currencies,
the gold-priced currency exchange, the bond-default price cap, and resource
offers / direct trades priced in a nation currency.

Runs against a real Postgres. This machine's shell can point at prod, so run
with `env -u DATABASE_PUBLIC_URL DATABASE_URL=<local throwaway db>`. Every
row these tests create is removed in the fixture's teardown.
"""

import os
import threading
import uuid
from decimal import Decimal

import pytest

from database import get_db_connection
from tests._db_cleanup import purge_users_where

pytestmark = [
    pytest.mark.no_server,
    pytest.mark.skipif(
        not os.getenv("DATABASE_PUBLIC_URL") and not os.getenv("DATABASE_URL"),
        reason="Requires Postgres (DATABASE_PUBLIC_URL or DATABASE_URL)",
    ),
]

START_GOLD = 1_000_000


def _q(sql, params=()):
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(sql, params)
        try:
            return db.fetchall()
        except Exception:
            return None


def _one(sql, params=()):
    rows = _q(sql, params)
    return rows[0][0] if rows else None


def _gold(uid):
    return int(_one("SELECT gold FROM stats WHERE id=%s", (uid,)))


def _own_currency(uid):
    return Decimal(_one("SELECT national_currency_balance FROM stats WHERE id=%s", (uid,)))


def _held(uid, issuer):
    v = _one("SELECT amount FROM currency_holdings WHERE user_id=%s AND issuer_id=%s", (uid, issuer))
    return Decimal(v or 0)


def _resource(uid, name):
    v = _one(
        "SELECT ue.quantity FROM user_economy ue JOIN resource_dictionary rd "
        "ON rd.resource_id = ue.resource_id WHERE ue.user_id=%s AND rd.name=%s",
        (uid, name),
    )
    return int(v or 0)


def _set_resource(uid, name, qty):
    _q(
        "INSERT INTO user_economy (user_id, resource_id, quantity) "
        "SELECT %s, resource_id, %s FROM resource_dictionary WHERE name=%s "
        "ON CONFLICT (user_id, resource_id) DO UPDATE SET quantity = EXCLUDED.quantity "
        "RETURNING user_id",
        (uid, qty, name),
    )


def _run(fn, *args):
    """Run a service call in its own committed transaction."""
    with get_db_connection() as conn:
        db = conn.cursor()
        return fn(db, *args)


@pytest.fixture
def nations():
    """Issuer A (with minted currency), and two other nations B and C."""
    ids = []
    with get_db_connection() as conn:
        db = conn.cursor()
        for key in ("a", "b", "c"):
            name = f"cmtest_{key}_{uuid.uuid4().hex[:8]}"
            db.execute(
                "INSERT INTO users (username, email, date, hash, auth_type) "
                "VALUES (%s, %s, '2026-09-27', '', 'normal') RETURNING id",
                (name, f"{name}@example.test"),
            )
            uid = db.fetchone()[0]
            db.execute(
                "INSERT INTO stats (id, location, gold, national_currency_balance) "
                "VALUES (%s, 'Grassland', %s, 0)",
                (uid, START_GOLD),
            )
            ids.append(uid)
        db.execute("UPDATE users SET currency_name='Amark' WHERE id=%s", (ids[0],))
    try:
        yield ids
    finally:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute("DELETE FROM currency_market_trades WHERE issuer_id = ANY(%s)", (ids,))
            db.execute("DELETE FROM currency_market_offers WHERE user_id = ANY(%s)", (ids,))
            db.execute("DELETE FROM currency_holdings WHERE user_id = ANY(%s) OR issuer_id = ANY(%s)", (ids, ids))
            db.execute("DELETE FROM offers WHERE user_id = ANY(%s)", (ids,))
            db.execute("DELETE FROM trades WHERE offerer = ANY(%s) OR offeree = ANY(%s)", (ids, ids))
            db.execute("DELETE FROM bonds WHERE issuer_id = ANY(%s) OR lender_id = ANY(%s)", (ids, ids))
            db.execute("DELETE FROM news WHERE destination_id = ANY(%s)", (ids,))
            db.execute("DELETE FROM national_currency_conversions WHERE user_id = ANY(%s)", (ids,))
            db.execute("DELETE FROM user_economy WHERE user_id = ANY(%s)", (ids,))
            for table, col in (("referral_active_days", "referred_user_id"),):
                db.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (ids,))
            db.execute("DELETE FROM stats WHERE id = ANY(%s)", (ids,))
            purge_users_where(db, 'id = ANY(%s)', (ids,))


def _mint(uid, units):
    from app_core.currency.services import mint_currency
    ok, err, _ = _run(mint_currency, uid, units)
    assert ok, err


def _give_b_currency(a, b, units, price="5"):
    """A sells `units` of its currency to B through the exchange."""
    from app_core.currency_market import services as cm
    ok, msg, _ = _run(cm.create_offer, a, a, "sell", units, price)
    assert ok, msg
    oid = _one("SELECT MAX(offer_id) FROM currency_market_offers WHERE user_id=%s", (a,))
    ok, msg, _ = _run(cm.accept_offer, b, oid, units)
    assert ok, msg


def _total_value(ids, issuer):
    """Gold held by the nations + gold in escrow, and every unit of the
    issuer's currency wherever it is (balances, holdings, sell escrow)."""
    gold = sum(_gold(u) for u in ids)
    gold += int(_one("SELECT COALESCE(SUM(gold_escrow),0) FROM currency_market_offers WHERE user_id = ANY(%s)", (ids,)))
    cur = _own_currency(issuer)
    cur += Decimal(_one("SELECT COALESCE(SUM(amount),0) FROM currency_holdings WHERE issuer_id=%s", (issuer,)))
    cur += Decimal(_one(
        "SELECT COALESCE(SUM(amount),0) FROM currency_market_offers WHERE issuer_id=%s AND type='sell'",
        (issuer,),
    ))
    return gold, cur


# ---------------------------------------------------------------------------
# exchange: escrow + refund
# ---------------------------------------------------------------------------

def test_buy_offer_escrows_gold_and_cancel_refunds_exactly(nations):
    from app_core.currency_market import services as cm
    a, b, _c = nations
    ok, msg, _ = _run(cm.create_offer, b, a, "buy", "10.5", "3.33")
    assert ok, msg
    escrow = int(Decimal("10.5") * Decimal("3.33"))  # floor(34.965) = 34
    assert _gold(b) == START_GOLD - escrow
    oid = _one("SELECT offer_id FROM currency_market_offers WHERE user_id=%s", (b,))
    assert _one("SELECT gold_escrow FROM currency_market_offers WHERE offer_id=%s", (oid,)) == escrow

    ok, msg, _ = _run(cm.cancel_offer, b, oid)
    assert ok, msg
    assert _gold(b) == START_GOLD
    assert _one("SELECT COUNT(*) FROM currency_market_offers WHERE offer_id=%s", (oid,)) == 0


def test_sell_offer_escrows_currency_and_cancel_refunds(nations):
    from app_core.currency_market import services as cm
    a, b, _c = nations
    _mint(a, 100)
    ok, msg, _ = _run(cm.create_offer, a, a, "sell", "40", "6")
    assert ok, msg
    assert _own_currency(a) == Decimal("60")
    oid = _one("SELECT offer_id FROM currency_market_offers WHERE user_id=%s", (a,))
    # someone else can't cancel it
    ok, _msg, _ = _run(cm.cancel_offer, b, oid)
    assert not ok
    ok, msg, _ = _run(cm.cancel_offer, a, oid)
    assert ok, msg
    assert _own_currency(a) == Decimal("100")


def test_create_rejects_unfunded_offers_without_side_effects(nations):
    from app_core.currency_market import services as cm
    a, b, _c = nations
    ok, _msg, _ = _run(cm.create_offer, b, a, "sell", "1", "5")  # B holds none
    assert not ok
    ok, _msg, _ = _run(cm.create_offer, b, a, "buy", "1000000", "5")  # 5M gold > 1M
    assert not ok
    assert _gold(b) == START_GOLD
    assert _one("SELECT COUNT(*) FROM currency_market_offers WHERE user_id=%s", (b,)) == 0


def test_foreign_holder_cannot_redeem(nations):
    from app_core.currency.services import redeem_currency
    a, b, _c = nations
    _mint(a, 50)
    _give_b_currency(a, b, "20")
    assert _held(b, a) == Decimal("20")
    ok, _err, _ = _run(redeem_currency, b, 5)  # only reads B's own currency
    assert not ok
    assert _held(b, a) == Decimal("20")


# ---------------------------------------------------------------------------
# exchange: value conservation
# ---------------------------------------------------------------------------

def test_value_is_conserved_across_partial_fills_and_round_trips(nations):
    from app_core.currency_market import services as cm
    a, b, c = nations
    ids = [a, b, c]
    _mint(a, 300)
    base_gold, base_cur = _total_value(ids, a)

    # A sells 120 at an awkward price; B and C take it in odd slices.
    assert _run(cm.create_offer, a, a, "sell", "120", "4.37")[0]
    sell_id = _one("SELECT offer_id FROM currency_market_offers WHERE user_id=%s AND type='sell'", (a,))
    for who, amt in ((b, "33.33"), (c, "0.77"), (b, "50"), (c, "1000")):  # last one clipped
        ok, msg, _ = _run(cm.accept_offer, who, sell_id, amt)
        assert ok, msg
        assert _total_value(ids, a) == (base_gold, base_cur)
    assert _one("SELECT COUNT(*) FROM currency_market_offers WHERE offer_id=%s", (sell_id,)) == 0

    # C posts a buy offer; B and A fill it in slices, then C cancels the rest.
    assert _run(cm.create_offer, c, a, "buy", "90", "3.99")[0]
    buy_id = _one("SELECT offer_id FROM currency_market_offers WHERE user_id=%s AND type='buy'", (c,))
    for who, amt in ((b, "10.01"), (a, "7.13"), (b, "3.3")):
        ok, msg, _ = _run(cm.accept_offer, who, buy_id, amt)
        assert ok, msg
        assert _total_value(ids, a) == (base_gold, base_cur)
    assert _run(cm.cancel_offer, c, buy_id)[0]
    assert _total_value(ids, a) == (base_gold, base_cur)

    # A buy offer filled completely returns its rounding leftover to its maker.
    assert _run(cm.create_offer, b, a, "buy", "3", "1.01")[0]  # escrow floor(3.03)=3
    full_id = _one("SELECT MAX(offer_id) FROM currency_market_offers WHERE user_id=%s", (b,))
    assert _run(cm.accept_offer, c, full_id, "1")[0]   # pays floor(1.01)=1
    assert _run(cm.accept_offer, c, full_id, "2")[0]   # pays floor(2.02)=2, offer done
    assert _one("SELECT COUNT(*) FROM currency_market_offers WHERE offer_id=%s", (full_id,)) == 0
    assert _total_value(ids, a) == (base_gold, base_cur)

    assert _one("SELECT COUNT(*) FROM currency_market_trades WHERE issuer_id=%s", (a,)) == 9


# ---------------------------------------------------------------------------
# exchange: double-accept race
# ---------------------------------------------------------------------------

def test_concurrent_accepts_cannot_overfill_an_offer(nations):
    from app_core.currency_market import services as cm
    a, b, c = nations
    _mint(a, 100)
    assert _run(cm.create_offer, a, a, "sell", "100", "5")[0]
    oid = _one("SELECT offer_id FROM currency_market_offers WHERE user_id=%s", (a,))

    barrier = threading.Barrier(2)
    results = {}

    def taker(uid):
        with get_db_connection() as conn:
            db = conn.cursor()
            barrier.wait()
            results[uid] = cm.accept_offer(db, uid, oid, "100")

    threads = [threading.Thread(target=taker, args=(u,)) for u in (b, c)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    wins = [u for u, r in results.items() if r[0]]
    assert len(wins) == 1, results
    winner = wins[0]
    loser = c if winner == b else b
    assert _held(winner, a) == Decimal("100")
    assert _held(loser, a) == 0
    assert _gold(winner) == START_GOLD - 500
    assert _gold(loser) == START_GOLD
    assert _gold(a) == START_GOLD - 500 + 500  # minted 500 gold worth, sold for 500


# ---------------------------------------------------------------------------
# debt cap
# ---------------------------------------------------------------------------

def _default_bond(issuer, lender, owed):
    _q(
        "INSERT INTO bonds (issuer_id, lender_id, principal, daily_interest_rate, term_days, "
        "status, garnishment_owed) VALUES (%s, %s, 1000, 0.01, 7, 'defaulted', %s) RETURNING id",
        (issuer, lender, owed),
    )


def test_cap_formula():
    from app_core.currency_market.services import cap_for_owed
    assert cap_for_owed(0) is None
    assert cap_for_owed(1) == Decimal("3.99")
    assert cap_for_owed(100_000) == Decimal("3.50")
    assert cap_for_owed(10_000_000) == Decimal("1.00")


def test_debt_cap_enforced_at_creation_and_acceptance(nations):
    from app_core.currency_market import services as cm
    a, b, c = nations
    _mint(a, 100)
    # Listed at 4.5 while A is solvent...
    assert _run(cm.create_offer, a, a, "sell", "10", "4.5")[0]
    oid = _one("SELECT offer_id FROM currency_market_offers WHERE user_id=%s", (a,))

    _default_bond(a, c, 20_000)  # cap = 4.0 - 0.1 = 3.90
    # ...can't be filled once A defaults,
    ok, msg, _ = _run(cm.accept_offer, b, oid, "1")
    assert not ok and "default" in msg
    assert _gold(b) == START_GOLD
    # new offers above the cap are refused (sell and buy alike),
    assert not _run(cm.create_offer, a, a, "sell", "10", "3.91")[0]
    assert not _run(cm.create_offer, b, a, "buy", "1", "4")[0]
    # at or under the cap is fine,
    assert _run(cm.create_offer, a, a, "sell", "10", "3.90")[0]
    # and once the debt is paid off the cap lifts.
    _q("UPDATE bonds SET garnishment_owed = 0 WHERE issuer_id=%s RETURNING id", (a,))
    ok, msg, _ = _run(cm.accept_offer, b, oid, "1")
    assert ok, msg


# ---------------------------------------------------------------------------
# resource trades priced in a currency
# ---------------------------------------------------------------------------

def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def test_currency_priced_sell_offer_settles_in_currency(nations, client):
    a, b, _c = nations
    _mint(a, 1000)
    _give_b_currency(a, b, "500")
    _set_resource(a, "oil", 100)

    _login(client, a)
    r = client.post("/post_offer/sell", data={"resource": "oil", "amount": "40", "price": "3", "currency_id": str(a)})
    assert r.status_code in (302, 303), r.data[:300]
    oid, cur = _q("SELECT offer_id, currency_id FROM offers WHERE user_id=%s", (a,))[0]
    assert cur == a
    assert _resource(a, "oil") == 60

    a_cur_before = _own_currency(a)
    gold_a, gold_b = _gold(a), _gold(b)
    _login(client, b)
    r = client.post(f"/buy_offer/{oid}", data={f"amount_{oid}": "10"})
    assert r.status_code in (302, 303), r.data[:300]
    # 10 * 3 = 30 units, 5% fee = 1 unit (rounded down), burned
    assert _resource(b, "oil") == 10
    assert _held(b, a) == Decimal("500") - 31
    assert _own_currency(a) == a_cur_before + 30
    assert (_gold(a), _gold(b)) == (gold_a, gold_b)  # no gold moved
    assert _one("SELECT amount FROM offers WHERE offer_id=%s", (oid,)) == 30

    # can't pay more than you hold (30 * 3 + 4 fee = 94 > 50)
    _q("UPDATE currency_holdings SET amount = 50 WHERE user_id=%s AND issuer_id=%s RETURNING 1", (b, a))
    r = client.post(f"/buy_offer/{oid}", data={f"amount_{oid}": "30"})
    assert r.status_code == 400
    assert _resource(b, "oil") == 10
    assert _held(b, a) == Decimal("50")
    assert _held(b, a) == Decimal("50")


def test_currency_priced_buy_offer_escrow_fill_and_refund(nations, client):
    a, b, _c = nations
    _mint(a, 1000)
    _give_b_currency(a, b, "300")
    _set_resource(a, "coal", 50)

    _login(client, b)
    r = client.post("/post_offer/buy", data={"resource": "coal", "amount": "20", "price": "10", "currency_id": str(a)})
    assert r.status_code in (302, 303), r.data[:300]
    oid = _one("SELECT offer_id FROM offers WHERE user_id=%s", (b,))
    assert _held(b, a) == Decimal("100")  # 200 escrowed

    a_cur = _own_currency(a)
    _login(client, a)
    r = client.post(f"/sell_offer/{oid}", data={f"amount_{oid}": "5"})
    assert r.status_code in (302, 303), r.data[:300]
    assert _resource(b, "coal") == 5
    assert _resource(a, "coal") == 45
    assert _own_currency(a) == a_cur + 50 - 2  # 5% fee burned

    _login(client, b)
    r = client.post(f"/delete_offer/{oid}")
    assert r.status_code in (302, 303)
    assert _held(b, a) == Decimal("100") + 150  # 15 left * 10 refunded in currency
    assert _gold(b) == START_GOLD - 1500  # only the exchange purchase (300 @ 5) cost gold


def test_filling_the_wrong_offer_type_is_refused(nations, client):
    a, b, _c = nations
    _set_resource(a, "iron", 10)
    _login(client, a)
    client.post("/post_offer/sell", data={"resource": "iron", "amount": "10", "price": "7"})
    oid = _one("SELECT offer_id FROM offers WHERE user_id=%s", (a,))
    _set_resource(b, "iron", 10)
    _login(client, b)
    r = client.post(f"/sell_offer/{oid}", data={f"amount_{oid}": "10"})
    assert r.status_code == 400
    assert _gold(b) == START_GOLD and _resource(b, "iron") == 10


def test_currency_priced_direct_trade(nations, client):
    a, b, _c = nations
    _mint(a, 1000)
    _give_b_currency(a, b, "200")
    _set_resource(a, "lead", 30)

    _login(client, a)
    r = client.post(f"/post_trade_offer/sell/{b}", data={"resource": "lead", "amount": "30", "price": "2", "currency_id": str(a)})
    assert r.status_code in (302, 303), r.data[:300]
    tid = _one("SELECT offer_id FROM trades WHERE offerer=%s", (a,))
    assert _resource(a, "lead") == 0
    a_cur = _own_currency(a)

    _login(client, b)
    r = client.post(f"/accept_trade/{tid}")
    assert r.status_code in (302, 303), r.data[:300]
    assert _resource(b, "lead") == 30
    assert _held(b, a) == Decimal("200") - 63  # 60 + 3 fee
    assert _own_currency(a) == a_cur + 60


def test_direct_sell_trade_delivers_escrow_not_a_second_copy(nations, client, monkeypatch):
    # A fresh DB hands out low trade ids; don't let them hit the prod-only
    # legacy pre-escrow ids (4, 5).
    from app_core.market import routes as market_routes
    monkeypatch.setattr(market_routes, "LEGACY_UNESCROWED_SELL_TRADE_IDS", frozenset())
    a, b, _c = nations
    _set_resource(a, "copper", 100)
    _login(client, a)
    client.post(f"/post_trade_offer/sell/{b}", data={"resource": "copper", "amount": "40", "price": "1"})
    tid = _one("SELECT offer_id FROM trades WHERE offerer=%s", (a,))
    assert _resource(a, "copper") == 60
    _login(client, b)
    r = client.post(f"/accept_trade/{tid}")
    assert r.status_code in (302, 303), r.data[:300]
    assert _resource(b, "copper") == 40
    assert _resource(a, "copper") == 60  # used to drop to 20


def test_pages_render(nations, client, monkeypatch):
    a, b, _c = nations
    _mint(a, 100)
    _give_b_currency(a, b, "10")
    _set_resource(a, "oil", 10)
    _login(client, a)
    client.post("/post_offer/sell", data={"resource": "oil", "amount": "5", "price": "2", "currency_id": str(a)})
    _login(client, b)
    r = client.get("/currency_market")
    assert r.status_code == 200
    assert b"Amark" in r.data
    for page in ("market", "my_offers", "marketoffer"):
        for v2 in ("", page):
            monkeypatch.setenv("THEME_V2_PAGES", v2)
            _login(client, a)
            r = client.get(f"/{page}" + ("/" if page == "marketoffer" else ""))
            assert r.status_code == 200, (page, v2)
            if page != "marketoffer":
                # order book shows "<price> Amark each" (2026-10-03 market rework)
                assert b"Amark" in r.data, (page, v2)


def test_country_page_shows_holdings_and_trade_currency_picker(nations, client, monkeypatch):
    a, b, _c = nations
    _mint(a, 100)
    _give_b_currency(a, b, "12")
    for v2 in ("", "country"):
        monkeypatch.setenv("THEME_V2_PAGES", v2)
        _login(client, b)
        r = client.get(f"/country/id={a}")
        assert r.status_code == 200, v2
        assert b"Paid in their currency" in r.data, v2
        if v2:
            r = client.get(f"/country/id={b}")
            assert r.status_code == 200
            assert b"Other nations&#39; currencies" in r.data or b"Other nations' currencies" in r.data
            assert b"Amark" in r.data


def test_legacy_pre_escrow_sell_trade_ids_take_from_seller():
    from app_core.market import routes as market_routes
    assert not market_routes._sell_trade_escrowed("4")
    assert not market_routes._sell_trade_escrowed(5)
    assert market_routes._sell_trade_escrowed("6")
