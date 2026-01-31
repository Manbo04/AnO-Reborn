import threading
from flask import Flask
import market
from tests.test_integration_market_edgecases import fake_get_db_connection_factory


def test_concurrent_accept_sell_offer(monkeypatch):
    # Simulate a sell trade where seller already removed resource when posting.
    # Two concurrent accept attempts by the offeree (buyer) should only produce one
    # successful transfer and the trade should be removed exactly once.
    # State schema used by fake factory: stats, resources, trades
    state = {
        "stats": {300: {"gold": 1000}, 400: {"gold": 0}},
        "resources": {300: {"rations": 0}, 400: {"rations": 10}},
        # trades[id] = (offeree, type, offerer, resource, amount, price)
        # trade id 99:
        #   offeree=300 (buyer), offerer=400 (seller) selling 5 rations at price 10
        "trades": {99: (300, "sell", 400, "rations", 5, 10)},
    }

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    results = []

    def accept_attempt():
        with test_app.test_request_context("/", method="POST", data={}):
            from flask import session

            session["user_id"] = 300
            res = market.accept_trade("99")
            results.append(res)

    # Run two threads concurrently
    t1 = threading.Thread(target=accept_attempt)
    t2 = threading.Thread(target=accept_attempt)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one should have succeeded with a redirect (not a 400 error tuple)
    success_count = sum(
        1 for r in results if not (isinstance(r, tuple) and r[1] == 400)
    )
    assert success_count == 1

    # Validate final state: trade removed and balances updated exactly once
    assert 99 not in state["trades"]
    assert state["resources"][300]["rations"] == 5
    assert state["resources"][400]["rations"] == 5
    assert state["stats"][400]["gold"] == 50  # 5*10
    # Buyer paid 50
    assert state["stats"][300]["gold"] == 950
