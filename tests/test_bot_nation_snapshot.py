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
