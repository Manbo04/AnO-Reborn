from flask import Flask
from database import query_cache
import province


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        # ownership check
        if "select id from provinces where id=%s and userid=%s" in sql_lower:
            # return id to indicate ownership
            self._last = (params[0],)
        elif "select gold from stats" in sql_lower:
            uid = params[0]
            self._last = (self.state["stats"][uid]["gold"],)
        elif "select farms from proinfra where id=%s" in sql_lower:
            pid = params[0]
            self._last = (self.state["proinfra"][pid].get("farms", 0),)
        elif "select " in sql_lower and "from resources" in sql_lower:
            # select resource on buy/sell in resource_stuff
            resource = sql_lower.split()[1]
            uid = params[0]
            self._last = (self.state["resources"][uid].get(resource, 0),)
        elif "from proinfra where id=" in sql_lower:
            # aggregated select to compute used land/city slots
            pid = params[0]
            # sum all values in the proinfra row (missing fields treated as 0)
            row = self.state["proinfra"].get(pid, {})
            total = sum(v for v in row.values())
            self._last = (total,)
        elif "select land from provinces where id=%s" in sql_lower:
            pid = params[0]
            self._last = (self.state["provinces"][pid]["land"],)
        elif "select citycount from provinces where id=%s" in sql_lower:
            pid = params[0]
            self._last = (self.state["provinces"][pid]["citycount"],)
        elif (
            "update stats set gold=gold-%s where id=(%s)" in sql_lower
            or "update stats set gold=gold-%s where id=%s" in sql_lower
        ):
            # subtraction
            amt = params[0]
            uid = params[1]
            self.state["stats"][uid]["gold"] -= amt
        elif "update proinfra set farms" in sql_lower:
            new_val = params[0]
            pid = params[1]
            self.state["proinfra"][pid]["farms"] = new_val
        elif "update resources set" in sql_lower and "%s" in sql_lower:
            # parameterized update like UPDATE resources SET lumber=%s WHERE id=%s
            new_amount = params[0]
            uid = params[1]
            left = sql.split("SET", 1)[1].split("WHERE")[0].strip()
            resource = left.split("=")[0].strip()
            self.state["resources"][uid][resource] = new_amount
        else:
            self._last = None

    def fetchone(self):
        return self._last


class FakeConn:
    def __init__(self, state):
        self.state = state

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.state)

    def commit(self):
        pass


def fake_get_db_connection_factory(state):
    class CM:
        def __enter__(self):
            return FakeConn(state)

        def __exit__(self, exc_type, exc, tb):
            return False

    return CM


def test_province_buy_integration(monkeypatch):
    # app fixture is a Flask app; but we can create context manually
    state = {
        "stats": {99: {"gold": 200000}},
        "proinfra": {10: {"farms": 0}},
        "resources": {99: {"lumber": 20}},
        "provinces": {10: {"land": 100, "citycount": 10}},
    }

    # seed cache
    query_cache.set("resources_99", {"lumber": 20}, ttl_seconds=30)
    assert query_cache.get("resources_99") is not None

    # monkeypatch DB helpers - provide a cursor context manager that yields a FakeCursor
    class FakeCursorCM:
        def __enter__(self):
            return FakeCursor(state)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "province.get_db_cursor", lambda cursor_factory=None: FakeCursorCM()
    )

    # create a test request context and set session
    test_app = Flask(__name__)
    # required for using session in test_request_context
    test_app.secret_key = "test-secret"
    with test_app.test_request_context("/", method="POST", data={"farms": "1"}):
        # provide a mock session via flask global
        from flask import session

        session["user_id"] = 99
        # call the view function directly
        _ = province.province_sell_buy("buy", "farms", 10)

    # check results: farms incremented, resources decreased and gold decreased
    assert state["proinfra"][10]["farms"] == 1
    # lumber cost per farm is 10 (see variables); initial 20 -> 10 left
    assert state["resources"][99]["lumber"] == 10
    assert state["stats"][99]["gold"] < 100000
    # cache invalidated
    assert query_cache.get("resources_99") is None
