"""Feature flag decision rule, bucketing, and fail-safe behaviour (no database needed)."""
import pytest

pytestmark = pytest.mark.no_server

from app_core import feature_flags as ff


def flag(enabled=True, pct=100):
    return {"enabled": enabled, "rollout_percent": pct}


def test_unknown_flag_uses_default():
    assert ff.decide(None, "x_flag", 1, default=False) is False
    assert ff.decide(None, "x_flag", 1, default=True) is True


def test_master_switch_off_beats_percent():
    assert ff.decide(flag(False, 100), "x_flag", 1, False) is False


def test_full_rollout_and_zero_rollout():
    assert ff.decide(flag(True, 100), "x_flag", None, False) is True
    assert ff.decide(flag(True, 0), "x_flag", 7, False) is False


def test_partial_rollout_needs_user_id():
    assert ff.decide(flag(True, 50), "x_flag", None, False) is False


def test_bucket_is_stable_and_in_range():
    seen = {ff.bucket("x_flag", uid) for uid in range(500)}
    assert all(0 <= b < 100 for b in seen)
    assert ff.bucket("x_flag", 42) == ff.bucket("x_flag", 42)


def test_percent_slice_is_roughly_right():
    on = sum(ff.decide(flag(True, 10), "canary_a", uid, False) for uid in range(5000))
    assert 350 <= on <= 650  # about 10% of 5000


def test_canary_grows_monotonically():
    small = {u for u in range(2000) if ff.decide(flag(True, 5), "canary_a", u, False)}
    large = {u for u in range(2000) if ff.decide(flag(True, 25), "canary_a", u, False)}
    assert small <= large


def test_different_flags_pick_different_nations():
    a = {u for u in range(2000) if ff.decide(flag(True, 10), "canary_a", u, False)}
    b = {u for u in range(2000) if ff.decide(flag(True, 10), "canary_b", u, False)}
    assert a != b


def test_key_validation():
    assert ff.valid_key("upkeep_v3")
    for bad in ("", "Up", "UPKEEP", "1abc", "a b", "x" * 80, "drop;table"):
        assert not ff.valid_key(bad)


def test_db_failure_keeps_last_good_value(monkeypatch):
    ff.invalidate()
    monkeypatch.setattr(ff, "_load_all", lambda: {"k_flag": {**flag(True, 100), "key": "k_flag"}})
    assert ff.is_on("k_flag", 1) is True

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(ff, "_load_all", boom)
    ff._flags(force=True)
    assert ff.is_on("k_flag", 1) is True  # last good value kept


def test_db_failure_with_no_cache_returns_default(monkeypatch):
    ff.invalidate()
    ff._cache.clear()

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(ff, "_load_all", boom)
    assert ff.is_on("never_seen", 1, default=False) is False
    assert ff.is_on("never_seen", 1, default=True) is True


def test_set_flag_rejects_bad_input():
    with pytest.raises(ValueError):
        ff.set_flag("BAD KEY", True, 10, "t")
    with pytest.raises(ValueError):
        ff.set_flag("good_key", True, 101, "t")
    with pytest.raises(ValueError):
        ff.set_flag("good_key", True, "abc", "t")
