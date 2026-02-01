from flask import Flask
from database import query_cache
import market
import sys
import threading
import copy

# Global lock to make FakeCursor.execute atomic across threads in tests
FAKE_DB_LOCK = threading.Lock()
# Simulated advisory locks for pg_try_advisory_lock / pg_advisory_unlock
FAKE_ADVISORY_LOCKS = set()


class FakeCursor:
    def __init__(self, state, global_state=None):
        # `state` is the working copy for this connection, `global_state` is
        # the shared state visible to all connections. Some operations (like
        # DELETE ... RETURNING) need to be atomic against the global state.
        self.state = state
        self._global_state = global_state if global_state is not None else state
        self._last = None

    def execute(self, sql, params=None):
        with FAKE_DB_LOCK:
            # Debug: show SQL being executed
            # print may be captured by pytest; use it for diagnosis
            if isinstance(sql, (tuple, list)):
                sql = sql[0]
            sql_lower = sql.lower()
            print(f"[FAKE_DB] EXECUTE: {sql_lower} params={params}")
            # Simulate advisory lock calls
            if "pg_try_advisory_lock" in sql_lower:
                lock_id = params[0]
                try:
                    lock_id = int(lock_id)
                except Exception:
                    pass
                print("[FAKE_DB] advisory locks before try:", FAKE_ADVISORY_LOCKS)
                if lock_id in FAKE_ADVISORY_LOCKS:
                    self._last = (False,)
                    print(f"[FAKE_DB] pg_try_advisory_lock({lock_id}) -> False")
                else:
                    FAKE_ADVISORY_LOCKS.add(lock_id)
                    # When a lock is acquired in a connection, refresh the
                    # connection's working snapshot to reflect the latest global
                    # state so subsequent SELECTs see the most recent data.
                    try:
                        self.state.clear()
                        self.state.update(copy.deepcopy(self._global_state))
                    except Exception:
                        pass
                    self._last = (True,)
                    print(f"[FAKE_DB] pg_try_advisory_lock({lock_id}) -> True")
                    print(f"[FAKE_DB] advisory locks after add: {FAKE_ADVISORY_LOCKS}")
                return
            if "pg_advisory_unlock" in sql_lower:
                lock_id = params[0]
                try:
                    lock_id = int(lock_id)
                except Exception:
                    pass
                FAKE_ADVISORY_LOCKS.discard(lock_id)
                self._last = (True,)
                return
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
            elif (
                "from resources where id" in sql_lower
                and sql_lower.strip().startswith("select")
            ):
                parts = sql_lower.split()
                resource = parts[1]
                uid = params[0]
                self._last = (self.state["resources"][uid].get(resource, 0),)
            # SELECT ... FROM trades WHERE offer_id=(%s)
            elif (
                "from trades where offer_id" in sql_lower
                and sql_lower.strip().startswith("select")
            ):
                tid = params[0]
                # allow numeric or string keys
                trade = self.state.get("trades", {}).get(tid) or self.state.get(
                    "trades", {}
                ).get(int(tid))
                self._last = trade
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
            # DELETE FROM trades WHERE offer_id=(%s) or with RETURNING
            elif "delete from trades where offer_id" in sql_lower:
                print(
                    "[FAKE_DB] matched delete from trades branch; returning?",
                    "returning" in sql_lower,
                )
                tid = params[0]
                # Truncate long sql string for readability
                try:
                    preview = sql_lower[:120]
                except Exception:
                    preview = sql_lower
                print(
                    "[FAKE_DB] delete branch entry:",
                    preview,
                    "params=",
                    params,
                    "tid=",
                    tid,
                    "type=",
                    type(tid),
                )
                # If a RETURNING clause is present, return the trade first then delete
                if "returning" in sql_lower:
                    try:
                        tid_int = int(tid)
                    except Exception:
                        tid_int = None

                    print(
                        "[FAKE_DB] trades before delete: "
                        f"{list(self.state.get('trades', {}).keys())}"
                    )

                    # Remove the trade from the GLOBAL state to simulate an
                    # atomic DELETE ... RETURNING across connections. We still
                    # set the cursor's last row to the popped trade so fetchone
                    # returns it.
                    popped = None
                    popped_key = None
                    if tid_int is not None and tid_int in (
                        self._global_state.get("trades", {}) or {}
                    ):
                        popped = self._global_state["trades"].pop(tid_int)
                        # also remove from working copy so commits don't reintroduce it
                        self.state.get("trades", {}).pop(tid_int, None)
                        popped_key = tid_int
                    elif tid in (self._global_state.get("trades", {}) or {}):
                        popped = self._global_state["trades"].pop(tid)
                        self.state.get("trades", {}).pop(tid, None)
                        popped_key = tid

                    print(
                        "[FAKE_DB] POP results: "
                        f"popped_key={popped_key!r}, trade={popped!r}"
                    )
                    self._last = popped
                    print(
                        "[FAKE_DB] trades keys after delete: "
                        f"{list(self._global_state.get('trades', {}).keys())}"
                    )
                else:
                    if tid in self.state.get("trades", {}):
                        del self.state["trades"][tid]
                    else:
                        del self.state["trades"][int(tid)]
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
            # Parameterized updates without RETURNING
            # e.g. UPDATE resources SET lumber=%s WHERE id=%s
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
                # Expect params like (amt, id, amt) for '-' case or (amt, id) for '+'
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
                # If RETURNING is present and a conditional WHERE,
                # params may be (amt, uid, amt)
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
        with FAKE_DB_LOCK:
            return self._last

    def fetchall(self):
        # not used in these tests, but provide empty
        return []


class FakeConn:
    def __init__(self, state):
        # Keep a reference to the global state and work on a deep copy to
        # simulate transactional behavior: uncommitted changes are local to
        # the connection until commit() is called (on normal exit of the
        # context manager). Record a snapshot so we can detect concurrent
        # modifications and avoid clobbering newer data.
        self._global_state = state
        self.state = copy.deepcopy(state)
        self._snapshot = copy.deepcopy(state)

    def cursor(self):
        return FakeCursor(self.state, self._global_state)

    def commit(self):
        # Merge working copy back to the global state, but only overwrite
        # values that haven't changed since we opened the connection (i.e.,
        # where the global value equals our snapshot). This prevents an
        # outer connection from clobbering newer commits made by inner
        # connections.
        for table, data in self.state.items():
            if isinstance(data, dict):
                g = self._global_state.setdefault(table, {})
                snap = self._snapshot.get(table, {}) or {}
                for k, v in copy.deepcopy(data).items():
                    # Safe to overwrite if the global value hasn't changed
                    if k not in g or g.get(k) == snap.get(k):
                        g[k] = v
                # Handle deletions: if a key existed in our snapshot but not in
                # our working copy, and the global still matches the snapshot,
                # then remove it globally (we deleted it in our transaction).
                removed = set((snap or {}).keys()) - set((data or {}).keys())
                for k in removed:
                    if g.get(k) == snap.get(k):
                        g.pop(k, None)
            else:
                if self._global_state.get(table) == self._snapshot.get(table):
                    self._global_state[table] = copy.deepcopy(data)


def fake_get_db_connection_factory(state):
    class CM:
        def __enter__(self):
            self._conn = FakeConn(state)
            return self._conn

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                # Normal exit -> commit
                try:
                    self._conn.commit()
                except Exception:
                    pass
            # Do not suppress exceptions
            return False

    return CM


# Tests


def test_fake_delete_returning_pops_trade_sequential(monkeypatch):
    state = {"trades": {99: (300, "sell", 400, "rations", 5, 10)}}
    cm = fake_get_db_connection_factory(state)()
    with cm as conn:
        db1 = conn.cursor()
        sql = (
            "DELETE FROM trades "
            "WHERE offer_id=(%s) "
            "RETURNING offeree, type, offerer, resource, amount, price"
        )
        db1.execute(sql, (99,))
        first = db1.fetchone()
        assert first is not None

        db2 = conn.cursor()
        sql2 = (
            "DELETE FROM trades "
            "WHERE offer_id=(%s) "
            "RETURNING offeree, type, offerer, "
            "resource, amount, price"
        )
        db2.execute(sql2, (99,))
        second = db2.fetchone()
        assert second is None


def test_fake_delete_returning_under_concurrency(monkeypatch):
    # Two threads calling DELETE ... RETURNING should not both return a trade
    state = {
        "trades": {99: (300, "sell", 400, "rations", 5, 10)},
        "stats": {},
        "resources": {},
    }
    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    results = []

    def do_delete():
        cm = fake_get_db_connection_factory(state)()
        with cm as conn:
            db = conn.cursor()
            sql = (
                "DELETE FROM trades "
                "WHERE offer_id=(%s) "
                "RETURNING offeree, type, offerer, "
                "resource, amount, price"
            )
            db.execute(sql, ("99",))  # simulate string param as well
            results.append(db.fetchone())

    # Run concurrently using top-level threading import
    t1 = threading.Thread(target=do_delete)
    t2 = threading.Thread(target=do_delete)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one should have returned a trade tuple
    assert sum(1 for r in results if r) == 1

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


def test_buy_market_offer_give_resource_failure(monkeypatch):
    # Simulate give_resource failing when bank -> buyer transfer attempted
    state = {
        "stats": {1000: {"gold": 1000}, 2000: {"gold": 100}},
        "resources": {1000: {"rations": 0}, 2000: {"rations": 10}},
        "offers": {
            10: {"resource": "rations", "amount": 10, "price": 10, "user_id": 2000}
        },
    }

    query_cache.set("resources_1000", {"rations": 0}, ttl_seconds=30)
    query_cache.set("resources_2000", {"rations": 10}, ttl_seconds=30)

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    # Make give_resource fail for the bank -> buyer transfer
    monkeypatch.setattr(
        "market.give_resource", lambda *a, **kw: "insufficient funds in bank"
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={"amount_10": "5"}):
        from flask import session

        session["user_id"] = 1000
        res = market.buy_market_offer("10")

    # Expect friendly error and no state change
    assert isinstance(res, tuple) and res[1] == 400
    assert state["offers"][10]["amount"] == 10
    assert state["resources"][1000]["rations"] == 0
    # caches should not be invalidated on failure
    assert query_cache.get("resources_1000") is not None
    assert query_cache.get("resources_2000") is not None


def test_report_trade_error_with_sentry(monkeypatch):
    # Ensure that _report_trade_error attaches extras and calls Sentry in a safe way
    called = {"msg": None, "extras": None}

    class DummyScope:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def set_extra(self, k, v):
            if not hasattr(self, "extras"):
                self.extras = {}
            self.extras[k] = v

    class DummySentry:
        def __init__(self):
            self.captured = []

        def push_scope(self):
            return DummyScope()

        def capture_message(self, msg):
            called["msg"] = msg

        def capture_exception(self, exc):
            called["msg"] = f"exc:{exc}"

    dummy = DummySentry()
    monkeypatch.setitem(sys.modules, "sentry_sdk", dummy)

    import market as mkt

    mkt._report_trade_error("boom", extra={"user_id": 999, "offer_id": 13})
    assert called["msg"] == "boom"


def test_accept_trade_give_resource_failure(monkeypatch):
    # Simulate a trade where give_resource fails during acceptance
    # trade row is (offeree, type, offerer, resource, amount, price)
    state = {
        "stats": {3000: {"gold": 1000}, 4000: {"gold": 100}},
        "resources": {3000: {"rations": 0}, 4000: {"rations": 10}},
        "trades": {42: (3000, "sell", 4000, "rations", 5, 10)},
    }

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    # Force give_resource to fail (e.g., money transfer fails)
    monkeypatch.setattr("market.give_resource", lambda *a, **kw: "transfer failed")

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={}):
        from flask import session

        session["user_id"] = 3000
        res = market.accept_trade("42")

    # Expect an error (400) and the trade should still exist (not deleted)
    assert isinstance(res, tuple) and res[1] == 400
    assert 42 in state["trades"]
    # Ensure no resource or money mutation happened
    assert state["resources"][3000]["rations"] == 0
    assert state["stats"][4000]["gold"] == 100


def test_accept_trade_give_resource_raises_exception(monkeypatch):
    # Simulate a trade where give_resource raises an exception during acceptance
    state = {
        "stats": {7000: {"gold": 1000}, 8000: {"gold": 500}},
        "resources": {7000: {"rations": 0}, 8000: {"rations": 10}},
        "trades": {99: (7000, "sell", 8000, "rations", 3, 10)},
    }

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    def raising_give(*a, **kw):
        raise Exception("boom")

    monkeypatch.setattr("market.give_resource", raising_give)

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={}):
        from flask import session

        session["user_id"] = 7000
        res = market.accept_trade("99")

    # Should return friendly error (400) and trade remains
    assert isinstance(res, tuple) and res[1] == 400
    assert 99 in state["trades"]
    assert state["resources"][7000]["rations"] == 0
    assert state["stats"][8000]["gold"] == 500


def test_accept_buy_offer_seller_lacks_resource_does_not_double_charge(monkeypatch):
    # Buyer posted a buy offer and had funds removed at posting.
    # Seller has no resources.
    state = {
        "stats": {100: {"gold": 950}, 200: {"gold": 0}},
        "resources": {100: {"rations": 0}, 200: {"rations": 0}},
        # trade format in this file's tests:
        # trades[id] = (offeree, type, offerer, resource, amount, price)
        # Here offerer=100 (buyer), offeree=200 (seller), type='buy'
        "trades": {42: (200, "buy", 100, "rations", 5, 10)},
    }

    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"

    # avoid Jinja template rendering in tests for error paths
    monkeypatch.setattr(
        "helpers.render_template", lambda *a, **kw: f"error:{kw.get('message','')}"
    )

    with test_app.test_request_context("/", method="POST", data={}):
        from flask import session

        session["user_id"] = 200  # seller trying to accept
        res = market.accept_trade("42")

    # Should return a 400 error because seller lacks resources; trade still present
    assert isinstance(res, tuple) and res[1] == 400
    assert 42 in state["trades"]
    # Ensure buyer was not double-charged (remains at 950)
    assert state["stats"][100]["gold"] == 950
    # Ensure seller didn't receive money
    assert state["stats"][200]["gold"] == 0
    # Ensure no resource mutation occurred
    assert state["resources"][200]["rations"] == 0
