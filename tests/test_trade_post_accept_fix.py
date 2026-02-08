from flask import Flask
from tests.test_integration_market_edgecases import fake_get_db_connection_factory
import market


def test_accept_sell_trade_where_seller_already_had_resource_removed(monkeypatch):
    # Simulate a user (seller) who posted a sell trade that already deducted
    # the resource from their account (e.g. old behaviour).
    # Buyer should still be able to accept and receive resources; seller
    # should be credited money.
    seller = 1000
    buyer = 2000

    state = {
        "stats": {seller: {"gold": 0}, buyer: {"gold": 1000}},
        # Seller had 525 and posted 500 -> now left with 25 (already removed)
        "resources": {seller: {"copper": 25}, buyer: {"copper": 0}},
        # Simulate an existing trade (offer_id=1):
        #  (offeree, type, offerer, resource, amount, price)
        "trades": {1: (buyer, "sell", seller, "copper", 500, 1)},
    }

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    with test_app.test_request_context("/", method="POST", data={}):
        from flask import session

        session["user_id"] = buyer  # buyer accepting
        res = market.accept_trade("1")

    # Successful accept should redirect to /my_offers
    assert res.status_code == 302

    # Buyer should receive the resource from escrow
    assert state["resources"][buyer]["copper"] == 500

    # Seller should be credited money (500 * 1)
    assert state["stats"][seller]["gold"] == 500

    # Trade should be removed
    assert 1 not in state["trades"]
