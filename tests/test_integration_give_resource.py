from database import query_cache
from market import give_resource


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._last = None

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        # SELECT gold FROM stats WHERE id=%s
        if "select gold from stats" in sql_lower:
            uid = params[0]
            self._last = (self.state["stats"][uid]["gold"],)
        # SELECT <resource> FROM resources WHERE id=%s
        elif "from resources where id" in sql_lower and sql_lower.strip().startswith(
            "select"
        ):
            # parse resource name (e.g. SELECT rations FROM resources WHERE id=%s)
            parts = sql_lower.split()
            # SELECT <resource> FROM
            resource = parts[1]
            uid = params[0]
            self._last = (self.state["resources"][uid].get(resource, 0),)
        # Updates: UPDATE stats SET gold=gold-... or +
        elif "update stats set gold" in sql_lower:
            # parameterized or not. If RETURNING and a conditional is used, params may be
            # (amt, uid, required) and we should only apply when sufficient funds exist.
            if "returning" in sql_lower:
                amt = params[0]
                uid = params[1]
                required = params[2]
                if self.state["stats"][uid]["gold"] < required:
                    self._last = None
                else:
                    if "-" in sql_lower:
                        self.state["stats"][uid]["gold"] -= amt
                    else:
                        self.state["stats"][uid]["gold"] += amt
                    self._last = (self.state["stats"][uid]["gold"],)
            else:
                if params:
                    amt = params[0]
                    uid = params[1]
                    # Determine if subtract or add
                    if "-" in sql_lower:
                        self.state["stats"][uid]["gold"] -= amt
                    else:
                        self.state["stats"][uid]["gold"] += amt
        # Updates for resources: UPDATE resources SET <res>=<res>+/-<amt>
        elif (
            "update resources set" in sql_lower
            and ("=" in sql_lower and "+" in sql_lower or "-" in sql_lower)
            and "returning" not in sql_lower
        ):
            # non-parameterized update used in give_resource
            # e.g. UPDATE resources SET rations=rations+100 WHERE id=%s
            left = sql_lower.split("set", 1)[1].split("where")[0].strip()
            # left is like 'rations=rations+100' or 'rations=rations-100' or 'rations=rations+%s'
            resource, expr = [p.strip() for p in left.split("=")]
            if "%s" in expr:
                # parameterized amount e.g. rations=rations+%s with params=(amt, uid)
                amt = params[0]
                uid = params[1]
                if "+" in expr:
                    self.state["resources"][uid][resource] = (
                        self.state["resources"][uid].get(resource, 0) + amt
                    )
                else:
                    self.state["resources"][uid][resource] = (
                        self.state["resources"][uid].get(resource, 0) - amt
                    )
            else:
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
        # Parameterized resource update used when taker gets resources in give_resource
        elif "update resources set" in sql_lower and "%s" in sql_lower:
            # handles queries like UPDATE resources SET resource=%s WHERE id=%s
            # or expressions like UPDATE resources SET resource=resource+%s WHERE id=%s
            left = sql.split("SET", 1)[1].split("WHERE")[0].strip()
            resource = left.split("=")[0].strip()
            if "+" in left:
                # e.g. resource=resource+%s -- params: (amt, uid)
                amt = params[0]
                uid = params[1]
                self.state["resources"][uid][resource] = (
                    self.state["resources"][uid].get(resource, 0) + amt
                )
                self._last = (self.state["resources"][uid][resource],)
            elif "-" in left:
                amt = params[0]
                uid = params[1]
                self.state["resources"][uid][resource] = (
                    self.state["resources"][uid].get(resource, 0) - amt
                )
                self._last = (self.state["resources"][uid][resource],)
            else:
                new_amount = params[0]
                uid = params[1]
                self.state["resources"][uid][resource] = new_amount
                self._last = (new_amount,)

        else:
            # Other statements not needed for this test
            self._last = None

    def fetchone(self):
        return self._last


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


def test_give_resource_integration(monkeypatch):
    # initial fake DB state
    state = {
        "stats": {42: {"gold": 1000}},
        "resources": {42: {"rations": 500, "lumber": 200}},
    }

    # seed cache for user 42
    query_cache.set("resources_42", {"rations": 500, "lumber": 200}, ttl_seconds=30)
    assert query_cache.get("resources_42") is not None

    # monkeypatch DB connection
    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )

    # perform a transfer from bank to user 42: add 100 rations
    res = give_resource("bank", 42, "rations", 100)
    assert res is True

    # resource updated
    assert state["resources"][42]["rations"] == 600

    # cache invalidated
    assert query_cache.get("resources_42") is None

    # test money transfer from user to bank
    query_cache.set("resources_42", {"rations": 600})
    monkeypatch.setattr(
        "market.get_db_connection", lambda: fake_get_db_connection_factory(state)()
    )
    res2 = give_resource(42, "bank", "money", 200)
    assert res2 is True
    assert state["stats"][42]["gold"] == 800
    assert query_cache.get("resources_42") is None
