"""The hub's viewer-independent numbers are built once, then served from cache."""
from app_core.main import routes
from database import query_cache


def test_hub_global_stats_built_once_then_cached(monkeypatch):
    query_cache.delete("hub_global_stats") if hasattr(query_cache, "delete") else None
    calls = []

    def fake_build():
        calls.append(1)
        return {"nations_online": 3, "news": []}

    monkeypatch.setattr(routes, "_build_hub_global_stats", fake_build)
    first = routes._hub_global_stats()
    second = routes._hub_global_stats()
    assert first == second == {"nations_online": 3, "news": []}
    assert len(calls) == 1
    query_cache.delete("hub_global_stats") if hasattr(query_cache, "delete") else None
