"""Every interactive event must be resolvable.

respond_event() raises "Unknown resource" (HTTP 500) for any cost/reward key it
cannot map to variables.RESOURCES, so a typo in events.json breaks that event
for every player who draws it.
"""
import json
import os

import pytest

import variables

pytestmark = pytest.mark.no_server

EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app_core", "events", "events.json",
)


def _events():
    with open(EVENTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    return data


def _split(key):
    return (key[:-4], True) if key.endswith("_pct") else (key, False)


def test_enough_events():
    assert len(_events()) >= 65


@pytest.mark.parametrize("event_id", sorted(_events()))
def test_event_is_well_formed(event_id):
    event = _events()[event_id]
    assert event["title"].strip() and event["description"].strip()
    options = event["options"]
    assert 2 <= len(options) <= 4
    for option in options:
        assert option["text"].strip()
        for spec in (option.get("costs", {}), option.get("rewards", {})):
            for key, value in spec.items():
                name, pct = _split(key)
                assert name == "gold" or name in variables.RESOURCES, f"{event_id}: unknown {name}"
                assert isinstance(value, int) and value > 0, f"{event_id}: bad amount for {key}"
                if pct:
                    assert value <= 25, f"{event_id}: {key}={value} is too large"


def test_event_ids_are_unique_titles():
    titles = [e["title"] for e in _events().values()]
    assert len(titles) == len(set(titles))
