import pytest
from datetime import datetime, timedelta, timezone
from wars import action_points

pytestmark = pytest.mark.no_server


def test_is_blockaded_false_when_no_blockade():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "attacker": 1,
            "defender": 2,
            "attacker_blockaded": None,
            "defender_blockaded": None,
            "defender_name": "Nation Two",
        }
    ]
    assert action_points.is_blockaded(1, rows, now) is False
    assert action_points.is_blockaded(2, rows, now) is False
    assert action_points.get_blockade_info(1, rows, now) is None


def test_is_blockaded_active():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    until = now + timedelta(hours=5)
    rows = [
        {
            "attacker": 1,
            "defender": 2,
            "attacker_blockaded": None,
            "defender_blockaded": until,
            "attacker_name": "Kingdom One",
            "defender_name": "Empire Two",
        }
    ]
    # Nation 1 is attacker, not blockaded
    assert action_points.is_blockaded(1, rows, now) is False
    # Nation 2 is defender, blockaded until 17:00 UTC
    assert action_points.is_blockaded(2, rows, now) is True

    info = action_points.get_blockade_info(2, rows, now)
    assert info is not None
    assert info["enemy_id"] == 1
    assert info["enemy_name"] == "Kingdom One"
    assert info["until"] == until
    assert info["formatted_until"] == "17:00 UTC"


def test_is_blockaded_expired():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=1)
    rows = [
        {
            "attacker": 1,
            "defender": 2,
            "attacker_blockaded": past,
            "defender_blockaded": None,
            "defender_name": "Nation Two",
        }
    ]
    # Expired 1 hour ago
    assert action_points.is_blockaded(1, rows, now) is False
    assert action_points.get_blockade_info(1, rows, now) is None


def test_is_blockaded_multiple_wars():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    until1 = now - timedelta(hours=2) # expired
    until2 = now + timedelta(hours=10) # active
    rows = [
        {
            "attacker": 1,
            "defender": 2,
            "attacker_blockaded": until1,
            "defender_blockaded": None,
            "defender_name": "Nation Two",
        },
        {
            "attacker": 3,
            "defender": 1,
            "attacker_blockaded": None,
            "defender_blockaded": until2,
            "attacker_name": "Nation Three",
        },
    ]
    assert action_points.is_blockaded(1, rows, now) is True
    info = action_points.get_blockade_info(1, rows, now)
    assert info is not None
    assert info["enemy_name"] == "Nation Three"
    assert info["formatted_until"] == "22:00 UTC"


def test_is_blockaded_tuple_rows():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    until = now + timedelta(hours=4)
    # (attacker, defender, attacker_blockaded, defender_blockaded, enemy_name)
    rows = [
        (1, 2, until, None, "Nation Two")
    ]
    assert action_points.is_blockaded(1, rows, now) is True
    assert action_points.is_blockaded(2, rows, now) is False
