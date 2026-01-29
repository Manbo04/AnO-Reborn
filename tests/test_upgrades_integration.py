from flask import Flask
from database import query_cache
import upgrades


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        # UPDATE stats SET gold=gold-%s WHERE id=%s AND gold>=%s RETURNING gold
        if "update stats set gold=gold-" in sql_lower and "returning gold" in sql_lower:
            amt = params[0]
            uid = params[1]
            if self.state["stats"][uid]["gold"] < amt:
                self._last = None
            else:
                self.state["stats"][uid]["gold"] -= amt
                self._last = (self.state["stats"][uid]["gold"],)
        elif (
            "update resources set" in sql_lower
            and "returning" in sql_lower
            and "-" in sql_lower
        ):
            # e.g. UPDATE resources SET lumber=lumber-%s WHERE id=%s AND lumber >= %s RETURNING lumber
            # params: (amt, id, amt)
            amt = params[0]
            uid = params[1]
            # simple parse to find the resource name
            left = sql_lower.split("set", 1)[1].split("where")[0].strip()
            resource = left.split("=")[0].strip()
            if self.state["resources"][uid].get(resource, 0) < amt:
                self._last = None
            else:
                self.state["resources"][uid][resource] -= amt
                self._last = (self.state["resources"][uid][resource],)
        elif "update upgrades set" in sql_lower:
            # e.g. UPDATE upgrades SET cheapermaterials=1 WHERE user_id=%s
            uid = params[0]
            left = sql_lower.split("set", 1)[1].split("where")[0].strip()
            key, val = left.split("=")
            key = key.strip()
            val = int(val.strip())
            self.state["upgrades"][uid][key] = val
            self._last = (1,)
        else:
            self._last = None

    def fetchone(self):
        return self._last


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor


def fake_get_db_cursor_factory(state):
    class CM:
        def __enter__(self):
            return FakeCursor(state)

        def __exit__(self, exc_type, exc, tb):
            return False

    return CM


def test_upgrade_buy_and_cache_invalidation(monkeypatch):
    # Setup state: user 10 has enough gold and lumber
    state = {
        "stats": {10: {"gold": 500000000}},
        "resources": {10: {"lumber": 1000, "steel": 2000, "aluminium": 1000}},
        "upgrades": {10: {}},
    }

    monkeypatch.setattr(
        "upgrades.get_db_cursor", lambda: fake_get_db_cursor_factory(state)()
    )

    # seed cache to ensure invalidation
    query_cache.set("upgrades_10", {"cheapermaterials": 0}, ttl_seconds=300)

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    with test_app.test_request_context("/", method="POST"):
        from flask import session

        session["user_id"] = 10
        # buy "cheapermaterials" which costs lumber 220 and money 22,000,000
        upgrades.upgrade_sell_buy("buy", "cheapermaterials")

    # verify changes applied
    assert state["stats"][10]["gold"] < 500000000
    assert state["resources"][10]["lumber"] < 1000
    assert state["upgrades"][10].get("cheapermaterials") == 1

    # cache invalidated
    assert query_cache.get("upgrades_10") is None
