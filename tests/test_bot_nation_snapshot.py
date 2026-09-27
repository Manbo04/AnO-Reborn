"""Bot nation snapshot resilience (wars schema + partial failures)."""
from unittest.mock import patch

from bot_api import _wars_schema, nation_snapshot_for_bot


def test_wars_schema_normalized_columns():
    rows = [("war_id",), ("attacker_id",), ("defender_id",), ("peace_date",)]
    with patch(
        "bot_api.QueryHelper.fetch_all",
        return_value=rows,
    ):
        import bot_api

        bot_api._wars_schema_cache = None
        schema = _wars_schema()
    assert schema["war_pk"] == "war_id"
    assert schema["attacker"] == "attacker_id"
    assert schema["defender"] == "defender_id"


def test_wars_schema_legacy_columns():
    rows = [("id",), ("attacker",), ("defender",), ("peace_date",)]
    with patch(
        "bot_api.QueryHelper.fetch_all",
        return_value=rows,
    ):
        import bot_api

        bot_api._wars_schema_cache = None
        schema = _wars_schema()
    assert schema["war_pk"] == "id"
    assert schema["attacker"] == "attacker"
    assert schema["defender"] == "defender"


def test_nation_snapshot_for_bot_returns_empty_on_total_failure():
    with patch(
        "bot_api._fetch_nation_snapshot_combined",
        side_effect=RuntimeError("db down"),
    ):
        assert nation_snapshot_for_bot(1) == {}


def test_nation_snapshot_uses_cache():
    import bot_api

    bot_api._snapshot_cache.clear()
    payload = {"id": 1, "username": "x", "gold": 0}
    with patch(
        "bot_api._fetch_nation_snapshot_combined",
        return_value=payload.copy(),
    ) as fetch:
        first = nation_snapshot_for_bot(1, full_detail=True)
        second = nation_snapshot_for_bot(1, full_detail=True)
    assert first["username"] == "x"
    assert second["username"] == "x"
    assert fetch.call_count == 1
    bot_api._snapshot_cache.clear()


def test_public_snapshot_has_province_stats_but_no_gold():
    import bot_api

    def fake_fetch_one(sql, params=None, dict_cursor=False):
        if "FROM users" in sql:
            return {"id": 5, "username": "Pharloom"}
        if "FROM stats" in sql:
            assert "gold" not in sql
            return {"location": "Boreal Forest"}
        if "FROM provinces" in sql:
            return {
                "province_count": 100,
                "total_population": 9_000_000,
                "total_land": 800,
                "total_cities": 6100,
                "avg_happiness": 55.0,
                "avg_productivity": 60.0,
            }
        raise AssertionError(sql)

    with patch("bot_api.QueryHelper.fetch_one", side_effect=fake_fetch_one), patch(
        "bot_api.get_influence", return_value=10
    ), patch("bot_api._coalition_summary", return_value={}), patch(
        "bot_api._active_war_count", return_value=0
    ), patch("bot_api._list_active_wars", return_value=[]):
        snap = nation_snapshot_for_bot(5, full_detail=False)

    assert snap["public_view"] is True
    assert "gold" not in snap
    assert "military" not in snap and "resources" not in snap
    assert snap["province_count"] == 100
    assert snap["provinces"]["total_cities"] == 6100
    assert snap["provinces"]["total_population"] == 9_000_000
