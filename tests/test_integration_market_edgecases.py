from flask import Flask
from database import query_cache
import market


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        # SELECT resource, amount, price, user_id FROM offers WHERE offer_id=(%s)
        offer_select = (
            "select resource, amount, price, user_id " "from offers where offer_id"
        )
        if offer_select in sql_lower:
            # params may be strings; support string or int keys
            offer_id = params[0]
            offer = self.state["offers"].get(offer_id)
            if offer is None:
                offer = self.state["offers"].get(int(offer_id))
            self._last = (
                offer["resource"],
                offer["amount"],
                offer["price"],
                offer["user_id"],
            )
        # SELECT gold FROM stats WHERE id=(%s)
        elif "select gold from stats" in sql_lower:
            uid = params[0]
            self._last = (self.state["stats"][uid]["gold"],)
        # SELECT <resource> FROM resources WHERE id=%s
        elif "from resources where id" in sql_lower and sql_lower.strip().startswith(
            "select"
        ):
            parts = sql_lower.split()
            resource = parts[1]
            uid = params[0]
            self._last = (self.state["resources"][uid].get(resource, 0),)
        # UPDATE offers SET amount=(%s) WHERE offer_id=(%s)
        elif "update offers set amount" in sql_lower:
            new_amount = params[0]
            offer_key = params[1]
            # support string keys coming from request
            offer = self.state["offers"].get(offer_key)
            if offer is None:
                offer = self.state["offers"].get(int(offer_key))
            if offer is not None:
                offer["amount"] = new_amount
        # DELETE FROM offers WHERE offer_id=(%s)
        elif "delete from offers where offer_id" in sql_lower:
            offer_key = params[0]
            if offer_key in self.state["offers"]:
                del self.state["offers"][offer_key]
            else:
                del self.state["offers"][int(offer_key)]
        # UPDATE resources SET <res>=%s WHERE id=%s or with RETURNING
        # Non-parameterized resource updates, e.g.:
        # "UPDATE resources SET rations=rations+5 WHERE id=%s"
        elif (
            "update resources set" in sql_lower
            and ("=" in sql_lower and ("+" in sql_lower or "-" in sql_lower))
            and "returning" not in sql_lower
        ):
            left = sql_lower.split("set", 1)[1].split("where")[0].strip()
            resource, expr = [p.strip() for p in left.split("=")]
            if "+" in expr:
                amount = int(expr.split("+")[1])
                op = "+"
            else:
                amount = int(expr.split("-")[1])
                op = "-"
            uid = params[0]
            if op == "+":
                self.state["resources"][uid][resource] = (
                    self.state["resources"][uid].get(resource, 0) + amount
                )
            else:
                self.state["resources"][uid][resource] = (
                    self.state["resources"][uid].get(resource, 0) - amount
                )
        # Parameterized updates without RETURNING (e.g. UPDATE resources SET lumber=%s WHERE id=%s)
        elif (
            "update resources set" in sql_lower
            and "%s" in sql_lower
            and "returning" not in sql_lower
        ):
            # Sometimes we also see patterns like
            # "...rations=rations+5 WHERE id=%s" with params=(id,)
            if len(params) == 1:
                # fallback to parsing non-parameterized expression
                uid = params[0]
                left = sql_lower.split("set", 1)[1].split("where")[0].strip()
                resource, expr = [p.strip() for p in left.split("=")]
                if "+" in expr:
                    amount = int(expr.split("+")[1])
                    self.state["resources"][uid][resource] = (
                        self.state["resources"][uid].get(resource, 0) + amount
                    )
                else:
                    amount = int(expr.split("-")[1])
                    self.state["resources"][uid][resource] = (
                        self.state["resources"][uid].get(resource, 0) - amount
                    )
            else:
                new_amount = params[0]
                uid = params[1]
                left = sql.split("SET", 1)[1].split("WHERE")[0].strip()
                resource = left.split("=")[0].strip()
                self.state["resources"][uid][resource] = new_amount
        # Parameterized updates with RETURNING (atomic checks)
        elif "update resources set" in sql_lower and "returning" in sql_lower:
            # Expect params like (amt, id, amt) for '-' case or (amt, id) for '+'.
            # Parse resource name
            left = sql_lower.split("set", 1)[1].split("where")[0].strip()
            resource = left.split("=")[0].strip()
            if "-" in left:
                amt = params[0]
                uid = params[1]
                required = params[2]
                if self.state["resources"][uid].get(resource, 0) < required:
                    self._last = None
                else:
                    self.state["resources"][uid][resource] -= amt
                    self._last = (self.state["resources"][uid][resource],)
            else:
                amt = params[0]
                uid = params[1]
                self.state["resources"][uid][resource] += amt
                self._last = (self.state["resources"][uid][resource],)

        # UPDATE stats SET gold=gold-%s WHERE id=(%s) (may include RETURNING)
        elif "update stats set gold=gold-%s" in sql_lower:
            # If RETURNING is present and a conditional WHERE, params may be (amt, uid, amt)
            if "returning" in sql_lower:
                amt = params[0]
                uid = params[1]
                required = params[2]
                if self.state["stats"][uid]["gold"] < required:
                    self._last = None
                else:
                    self.state["stats"][uid]["gold"] -= amt
                    self._last = (self.state["stats"][uid]["gold"],)
            else:
                amt = params[0]
                uid = params[1]
                self.state["stats"][uid]["gold"] -= amt
        # UPDATE stats SET gold=gold+%s WHERE id=%s
        elif (
            "update stats set gold=gold+%s" in sql_lower
            or "update stats set gold=gold+%s where id=%s" in sql_lower
        ):
            amt = params[0]
            uid = params[1]
            self.state["stats"][uid]["gold"] += amt
        # INSERT INTO offers ... (only used in post_offer not in these tests)
        else:
            self._last = None

    def fetchone(self):
        return self._last

    def fetchall(self):
        # not used in these tests, but provide empty
        return []


class FakeConn:
    def __init__(self, state):
        self.state = state

    def cursor(self):
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


# Tests


def test_buy_market_offer_insufficient_gold(monkeypatch):
    # Buyer has insufficient gold
    state = {
        "stats": {100: {"gold": 20}, 200: {"gold": 500}},
        "resources": {100: {"rations": 0}, 200: {"rations": 50}},
        "offers": {
            1: {"resource": "rations", "amount": 10, "price": 10, "user_id": 200}
        },
    }

    # seed caches to ensure invalidation would occur on success
    query_cache.set("resources_100", {"rations": 0}, ttl_seconds=30)
    query_cache.set("resources_200", {"rations": 50}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={"amount_1": "10"}):
        from flask import session

        session["user_id"] = 100
        res = market.buy_market_offer("1")

    # Expect error response tuple and no state mutation
    assert isinstance(res, tuple) and res[1] == 400
    assert state["offers"][1]["amount"] == 10
    assert state["resources"][100]["rations"] == 0
    # caches should not be invalidated on failure
    assert query_cache.get("resources_100") is not None
    assert query_cache.get("resources_200") is not None


def test_buy_market_offer_partial_fill_success(monkeypatch):
    # Buyer has enough gold to buy part of the offer
    state = {
        "stats": {100: {"gold": 1000}, 200: {"gold": 100}},
        "resources": {100: {"rations": 0}, 200: {"rations": 10}},
        "offers": {
            1: {"resource": "rations", "amount": 10, "price": 10, "user_id": 200}
        },
    }

    query_cache.set("resources_100", {"rations": 0}, ttl_seconds=30)
    query_cache.set("resources_200", {"rations": 10}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    with test_app.test_request_context("/", method="POST", data={"amount_1": "5"}):
        from flask import session

        session["user_id"] = 100
        res = market.buy_market_offer("1")

    # Should redirect on success (Flask redirect object)
    assert res.status_code == 302

    # resources and money moved
    assert state["resources"][100]["rations"] == 5
    assert state["stats"][200]["gold"] == 150  # seller gained 5*10

    # offer updated to remaining amount
    assert state["offers"][1]["amount"] == 5

    # caches invalidated for both users
    assert query_cache.get("resources_100") is None
    assert query_cache.get("resources_200") is None


def test_sell_market_offer_insufficient_resources(monkeypatch):
    # Seller does not have enough resource to sell
    state = {
        "stats": {300: {"gold": 100}, 400: {"gold": 100}},
        "resources": {300: {"lumber": 1}, 400: {"lumber": 0}},
        "offers": {2: {"resource": "lumber", "amount": 5, "price": 20, "user_id": 400}},
    }

    query_cache.set("resources_300", {"lumber": 1}, ttl_seconds=30)
    query_cache.set("resources_400", {"lumber": 0}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    with test_app.test_request_context("/", method="POST", data={"amount_2": "5"}):
        from flask import session

        session["user_id"] = 300
        res = market.sell_market_offer("2")

    assert isinstance(res, tuple) and res[1] == 400
    # no changes
    assert state["resources"][300]["lumber"] == 1
    assert state["offers"][2]["amount"] == 5
    assert query_cache.get("resources_300") is not None


def test_sell_market_offer_full_match_success(monkeypatch):
    # Seller sells to a buy offer fully
    state = {
        "stats": {300: {"gold": 100}, 400: {"gold": 500}},
        "resources": {300: {"lumber": 10}, 400: {"lumber": 0}},
        "offers": {2: {"resource": "lumber", "amount": 5, "price": 20, "user_id": 400}},
    }

    query_cache.set("resources_300", {"lumber": 10}, ttl_seconds=30)
    query_cache.set("resources_400", {"lumber": 0}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    with test_app.test_request_context("/", method="POST", data={"amount_2": "5"}):
        from flask import session

        session["user_id"] = 300
        res = market.sell_market_offer("2")

    # redirect on success
    assert res.status_code == 302

    # seller resource decreased by 5
    assert state["resources"][300]["lumber"] == 5

    # buyer (400) paid seller: seller gold increased by 100
    assert state["stats"][300]["gold"] == 200

    # offer removed
    assert 2 not in state["offers"]


def test_concurrent_transfers_invalidate_cache(monkeypatch):
    # Simulate two transfers in quick succession affecting same user
    state = {
        "stats": {500: {"gold": 1000}, 600: {"gold": 100}},
        "resources": {500: {"rations": 100}, 600: {"rations": 0}},
    }

    # seed cache
    query_cache.set("resources_500", {"rations": 100}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    with test_app.test_request_context(
        "/", method="POST", data={"amount": "10", "resource": "rations"}
    ):
        from flask import session

        session["user_id"] = 500
        # call transfer endpoint logic directly (transfer returns a redirect response)
        res1 = market.transfer(600)

    # Do a second transfer
    with test_app.test_request_context(
        "/", method="POST", data={"amount": "20", "resource": "rations"}
    ):
        from flask import session

        session["user_id"] = 500
        res2 = market.transfer(600)

    # both succeeded
    assert res1.status_code == 302
    assert res2.status_code == 302

    # final resources: 100 - 10 - 20 = 70
    assert state["resources"][500]["rations"] == 70
    assert state["resources"][600]["rations"] == 30

    # cache invalidated after operations
    assert query_cache.get("resources_500") is None


def test_transfer_insufficient_resources(monkeypatch):
    state = {
        "stats": {700: {"gold": 0}, 800: {"gold": 0}},
        "resources": {700: {"lumber": 5}, 800: {"lumber": 0}},
    }

    query_cache.set("resources_700", {"lumber": 5}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )
    with test_app.test_request_context(
        "/", method="POST", data={"amount": "20", "resource": "lumber"}
    ):
        from flask import session

        session["user_id"] = 700
        res = market.transfer(800)

    # Expect error tuple returned and no mutation
    assert isinstance(res, tuple) and res[1] == 400
    assert state["resources"][700]["lumber"] == 5
    assert query_cache.get("resources_700") is not None

    # caches invalidated
    assert query_cache.get("resources_300") is None
    assert query_cache.get("resources_400") is None
