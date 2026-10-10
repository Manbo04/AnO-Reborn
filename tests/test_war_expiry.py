import pytest

pytestmark = pytest.mark.no_server

from app_core.game_ticks.war_expiry import war_expired, format_war_auto_end, WAR_EXPIRY_DAYS


def test_war_expired_constants():
    assert WAR_EXPIRY_DAYS == 7


def test_war_expired_edge_cases():
    assert war_expired(None, 1000.0) is False
    assert war_expired(1000.0, None) is False
    assert war_expired(None, None) is False


def test_war_expired_timing():
    start = 1_000_000.0
    seven_days = 7 * 86400.0

    # 1 second before 7 days -> Not expired
    now_before = start + seven_days - 1.0
    assert war_expired(start, now_before) is False

    # Exactly 7 days -> Expired
    now_exact = start + seven_days
    assert war_expired(start, now_exact) is True

    # After 7 days -> Expired
    now_after = start + seven_days + 3600.0
    assert war_expired(start, now_after) is True

    # Custom days parameter
    assert war_expired(start, start + 3 * 86400, days=3) is True
    assert war_expired(start, start + 2 * 86400, days=3) is False


def test_format_war_auto_end():
    start = 1_000_000.0
    seven_days = 7 * 86400.0

    # Brand new war (7 days left): exactly 7d 0h
    assert format_war_auto_end(start, now=start) == "Ends automatically in 7d 0h"

    # 3 days and 4 hours left
    # 7 days - (3 days + 4 hours) = 4 days - 4 hours = 3 days 20 hours elapsed
    now_remaining = start + seven_days - (3 * 86400 + 4 * 3600)
    assert format_war_auto_end(start, now=now_remaining) == "Ends automatically in 3d 4h"

    # Expired war -> 0d 0h
    assert format_war_auto_end(start, now=start + seven_days + 100) == "Ends automatically in 0d 0h"
    assert format_war_auto_end(None) == "Ends automatically in 0d 0h"
