import database
from database import QueryCache, cache_response, QueryHelper
from AnO.app import app


def test_querycache_set_get_invalidate():
    qc = QueryCache(ttl_seconds=60)
    qc.set("k1", 123)
    assert qc.get("k1") == 123

    qc.set("prefix_key", 5)
    qc.invalidate(pattern="prefix")
    assert qc.get("prefix_key") is None

    qc.invalidate()
    assert qc.get("k1") is None


def test_cache_response_uses_ttl_and_session(monkeypatch):
    # Create a time source we control
    now = [1000]
    monkeypatch.setattr(database, "time", lambda: now[0])

    calls = {"count": 0}

    @cache_response(ttl_seconds=10)
    def page():
        calls["count"] += 1
        return f'value-{calls["count"]}'

    with app.test_request_context(path="/test"):
        # first call computes and caches
        v1 = page()
        assert v1 == "value-1"
        # second call within ttl returns cached
        v2 = page()
        assert v2 == "value-1"
        # advance time beyond ttl
        now[0] += 11
        v3 = page()
        assert v3 == "value-2"


def test_queryhelper_fetch_one_monkeypatched_cursor(monkeypatch):
    class FakeCursor:
        def __init__(self, result):
            self._result = result

        def execute(self, q, params=None):
            self._executed = (q, params)

        def fetchone(self):
            return self._result

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self._cursor

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_cursor = FakeCursor((42,))
    monkeypatch.setattr(
        database, "get_db_cursor", lambda *a, **kw: FakeCtx(fake_cursor)
    )

    res = QueryHelper.fetch_one("SELECT 1", None)
    assert res == (42,)
