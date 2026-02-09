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

    # Ensure advisory lock check won't skip the task in this test
    monkeypatch.setattr("tasks.try_pg_advisory_lock", lambda conn, lock_id, label: True)

    # Provide a tiny DB implementation that yields one province so the
    # function runs its main loop and emits the metric
    class SimpleCursor:
        def __init__(self):
            self._last = None

        def execute(self, sql, params=None):
            sql_lower = sql.strip().lower()
            # Return one province id from the chunked select
            if "select proinfra.id, provinces.userid" in sql_lower:
                # Return one province row: (proInfra.id, userId, land, productivity)
                self._last = [(1, 1, 1, 50)]
            elif sql_lower.startswith("select last_id from task_cursors"):
                self._last = (0,)
            elif sql_lower.startswith("select last_run from task_runs"):
                self._last = (None,)
            elif sql_lower.startswith("select * from proinfra"):
                # Return a dict-like row compatible with RealDictCursor usage
                try:
                    import variables

                    proinfra_row = {b: 0 for b in variables.BUILDINGS}
                except Exception:
                    proinfra_row = {"coal_burners": 0}
                proinfra_row["id"] = 1
                self._last = [proinfra_row]
            elif sql_lower.startswith("select id, happiness"):
                # provinces row returned to compute defaults
                self._last = [
                    {
                        "id": 1,
                        "happiness": 50,
                        "productivity": 50,
                        "pollution": 0,
                        "consumer_spending": 50,
                        "energy": 0,
                        "population": 0,
                    }
                ]
            else:
                self._last = None

        def fetchall(self):
            if isinstance(self._last, list):
                return self._last
            return []

        def fetchone(self):
            if isinstance(self._last, tuple):
                return self._last
            return None

    class SimpleConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, cursor_factory=None, **kwargs):
            return SimpleCursor()

        def commit(self):
            pass

    monkeypatch.setattr("database.get_db_connection", lambda: SimpleConn())

    # Call the function directly
    tasks.generate_province_revenue()

    assert called["ok"] is True
