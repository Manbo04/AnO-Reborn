import sys
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.no_server

for _m in ["flask", "flask_limiter", "flask_limiter.util", "flask_socketio",
           "flask_login", "flask_wtf", "flask_wtf.csrf", "extensions",
           "psycopg2", "psycopg2.extras", "psycopg2.pool",
           "psycopg2.extensions", "celery", "redis", "dotenv"]:
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            sys.modules[_m] = MagicMock()

from app_core.game_ticks.population import (  # noqa: E402
    rations_spoilage,
    rations_storage_buffer,
)


def test_storage_buffer_sums_buildings():
    assert rations_storage_buffer([("distribution_centers", 3), ("malls", 1)]) == (
        3 * 2_000_000 + 6_666_667
    )
    assert rations_storage_buffer([]) == 0


def test_no_spoilage_below_buffer():
    # need 100/h -> baseline buffer 33,600
    assert rations_spoilage(33_600, 100, 0) == 0
    assert rations_spoilage(1_000, 100, 0) == 0


def test_spoilage_is_two_percent_of_excess():
    assert rations_spoilage(133_600, 100, 0) == 2_000
    assert rations_spoilage(133_600, 100, 50_000) == 1_000
