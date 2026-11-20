"""Flag gate for upkeep v2 and the sell lock message (raid fix)."""
from datetime import datetime, timezone

import pytest

from app_core.economy import military_upkeep_v2 as v2


@pytest.mark.no_server
def test_explicit_now_ignores_the_flag(monkeypatch):
    import app_core.feature_flags as ff

    monkeypatch.setattr(ff, "is_on", lambda *a, **k: False)
    assert v2.v2_active(v2.UPKEEP_V2_START)
    assert not v2.v2_active(datetime(2026, 11, 6, 18, 59, tzinfo=timezone.utc))


@pytest.mark.no_server
def test_v2_follows_the_flag_after_the_start_date(monkeypatch):
    import app_core.feature_flags as ff

    seen = []

    def fake_is_on(key, user_id=None, default=False):
        seen.append(key)
        return key == "military_upkeep_v2" and state["on"]

    state = {"on": False}
    monkeypatch.setattr(ff, "is_on", fake_is_on)
    assert v2.v2_active() is False  # flag off: legacy upkeep
    state["on"] = True
    assert v2.v2_active() is True
    assert set(seen) == {"military_upkeep_v2"}


@pytest.mark.no_server
def test_sell_lock_message_rounds_up_to_whole_minutes():
    from app_core.military.services import SELL_LOCK_HOURS, sell_lock_message

    assert SELL_LOCK_HOURS * 3600 > 3600  # longer than one hourly upkeep tick
    assert "1 min" in sell_lock_message(1)
    assert "1 min" in sell_lock_message(60)
    assert "2 min" in sell_lock_message(61)
    assert "120 min" in sell_lock_message(7200)
