from flask import Flask, session

try:
    import market
    import app as app_module
except Exception:
    import os
    import sys

    # Running tests directly may not have project root on sys.path; add fallback
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import market
    import app as app_module

from tests.test_integration_market_edgecases import fake_get_db_connection_factory


def test_fmt_rounding_can_mislead():
    # 8,950,000 -> fmt returns rounded million and may display "9M"
    val = 8950000
    formatted = app_module.fmt(val)
    # Ensure the current fmt behavior can round and thus be misleading
    assert formatted in ("8.9M", "9M", "9.0M")


def test_sell_trade_credits_exact_amount(monkeypatch):
    # Seller (offerer) has copper and 0 gold; buyer (offeree) has enough gold
    seller = 5000
    buyer = 6000
    state = {
        "stats": {seller: {"gold": 0}, buyer: {"gold": 100000}},
        "resources": {seller: {"copper": 224}, buyer: {"copper": 24}},
        # trade tuple: (offeree, type, offerer, resource, amount, price)
        "trades": {123: (buyer, "sell", seller, "copper", 100, 100)},
    }

    # Use existing fake DB helper from tests
    # monkeypatch market.get_db_connection to use fake connection with our state
    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    # Avoid Jinja rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={}):
        session["user_id"] = buyer
        market.accept_trade("123")

    # Trade should be removed
    assert 123 not in state["trades"]

    # Resources transferred: seller copper decreased, buyer copper increased
    assert state["resources"][seller]["copper"] == 124
    assert state["resources"][buyer]["copper"] == 124

    # Money transferred: buyer gold decreased by 100*100, seller increased same
    assert state["stats"][buyer]["gold"] == 90000
    assert state["stats"][seller]["gold"] == 10000
