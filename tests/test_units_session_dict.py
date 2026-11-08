"""Regression: special (ICBM) attacks returned a 500 after consuming the missile.

``special_fight`` lazily adds a ``set`` (``_unusable_units_cache``) to the
attacker's ``Units`` object. The war routes stored the live ``__dict__`` in the
session, so saving the session cookie raised ``TypeError: Object of type set is
not JSON serializable``. ``session_dict()`` must be JSON-safe at all times.
"""

import json
import re
from pathlib import Path

import pytest

from units import Units

pytestmark = pytest.mark.no_server


def _units():
    u = Units(16, war_id=7)
    u.selected_units = {"icbms": 1}
    u.selected_units_list = ["icbms"]
    return u


def test_session_dict_is_json_safe_with_populated_cache():
    u = _units()
    u._unusable_units_cache = {"bombers", "tanks"}  # what a fight leaves behind
    json.dumps(u.session_dict())  # must not raise
    assert "_unusable_units_cache" not in u.session_dict()
    # the live object keeps its cache
    assert u._unusable_units_cache == {"bombers", "tanks"}


def test_session_dict_round_trips_through_rebuild():
    u = _units()
    u._unusable_units_cache = {"tanks"}
    rebuilt = Units.rebuild_from_dict(u.session_dict())
    assert rebuilt.user_id == 16
    assert rebuilt.war_id == 7
    assert rebuilt.selected_units == {"icbms": 1}
    assert rebuilt.selected_units_list == ["icbms"]


def test_routes_never_store_live_units_dict_in_session():
    src = Path(__file__).resolve().parents[1].joinpath("wars", "routes.py").read_text()
    assert not re.search(r"session\[[\"']attack_units[\"']\]\s*=\s*\w+\.__dict__", src)
