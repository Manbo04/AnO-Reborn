from flask import Flask, session

try:
    import market
    import trade_agreements
except Exception:
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import market
    import trade_agreements

from tests.test_integration_market_edgecases import fake_get_db_connection_factory


def test_market_accept_trade_emits_log(monkeypatch):
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

    calls = []

    def fake_logger(msg, *args, **kwargs):
        calls.append((msg, kwargs))

    monkeypatch.setattr(market, "logger", type("L", (), {"info": fake_logger}))

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={}):
        session["user_id"] = buyer
        market.accept_trade("123")

    # Ensure logger.info was called with our structured message
    assert any(
        c[0] == "trade_executed" for c in calls
    ), f"No trade_executed log found: {calls}"
    # check extra fields present inside kwargs['extra']
    kw = [c for c in calls if c[0] == "trade_executed"][0][1]
    assert "extra" in kw and isinstance(kw["extra"], dict)
    assert "amount" in kw["extra"] and "price" in kw["extra"]


def test_trade_agreement_exec_emits_log(monkeypatch):
    # Create a minimal agreement state
    proposer = 7000
    receiver = 8000
    state = {
        "stats": {proposer: {"gold": 1000}, receiver: {"gold": 500}},
        "resources": {proposer: {"rations": 10}, receiver: {"rations": 10}},
        "trade_agreements": {
            1: (
                1,
                proposer,
                "rations",
                1,
                receiver,
                "rations",
                1,
                0,
                None,
                24,
            )
        },
    }

    # Monkeypatch DB access to use fake state
    monkeypatch.setattr(
        "trade_agreements.get_db_connection",
        lambda: fake_get_db_connection_factory(state)(),
    )

    calls = []

    def fake_logger(msg, *args, **kwargs):
        calls.append((msg, kwargs))

    monkeypatch.setattr(
        trade_agreements, "logger", type("L", (), {"info": fake_logger})
    )

    success, msg = trade_agreements.execute_trade_agreement(1)
    assert success is True
    assert any(
        c[0] == "trade_agreement_executed" for c in calls
    ), f"No trade_agreement_executed log found: {calls}"
