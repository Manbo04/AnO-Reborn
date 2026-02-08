from flask import Flask, session

try:
    import market
    import tasks
except Exception:
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import market
    import tasks

from tests.test_integration_market_edgecases import fake_get_db_connection_factory


def test_accept_trade_records_trade(monkeypatch):
    seller = 5000
    buyer = 6000
    state = {
        "stats": {seller: {"gold": 0}, buyer: {"gold": 100000}},
        "resources": {seller: {"copper": 224}, buyer: {"copper": 24}},
        "trades": {123: (buyer, "sell", seller, "copper", 100, 100)},
    }

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    called = {"ok": False}

    def fake_rec(offer_id, offerer, offeree, resource, amount, price, trade_type=None):
        called["ok"] = True
        assert str(offer_id) == "123"
        assert int(offerer) == seller
        assert int(offeree) == buyer
        assert resource == "copper"
        assert int(amount) == 100
        assert int(price) == 100

    monkeypatch.setattr("helpers.record_trade_event", fake_rec)

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    with test_app.test_request_context("/", method="POST", data={}):
        session["user_id"] = buyer
        market.accept_trade("123")

    assert called["ok"] is True


def test_generate_province_revenue_records_metric(monkeypatch):
    # Small state sufficient for the function to run and finish quickly
    state = {
        "stats": {},
        "resources": {},
        "proInfra": [],
        "provinces": [],
    }

    # The functions import get_db_connection from the database module, so patch that
    monkeypatch.setattr(
        "database.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    called = {"ok": False}

    def fake_metric(name, duration):
        called["ok"] = True
        assert name == "generate_province_revenue"
        assert duration >= 0

    monkeypatch.setattr("helpers.record_task_metric", fake_metric)

    # Call the function directly
    tasks.generate_province_revenue()

    assert called["ok"] is True
