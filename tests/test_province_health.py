from contextlib import contextmanager

import pytest

from app_core.economy import province_health as ph

pytestmark = pytest.mark.no_server


class _Cur:
    def execute(self, sql, params=()):
        self.params = params

    def fetchall(self):
        # (province_id, city units used, land units used)
        return [(1, 5, 5), (2, 2, 1)]


def _setup(monkeypatch, power):
    @contextmanager
    def fake_cursor(*a, **k):
        yield _Cur()

    monkeypatch.setattr(ph, "get_request_cursor", fake_cursor)
    monkeypatch.setattr(ph, "nation_province_power", lambda uid, provs: power)


# (name, id, population, cityCount, land, happiness, productivity)
ROWS = [
    ("Alpha", 1, 100, 5, 5, 90, 50),
    ("Beta", 2, 200, 5, 5, 20, 50),
    ("Gamma", 3, 300, 5, 5, 70, 50),
]


def test_worst_first_and_totals(monkeypatch):
    power = {
        1: {"has_power": True, "consumption": 10, "production": 12},
        2: {"has_power": True, "consumption": 4, "production": 5},
        3: {"has_power": False, "consumption": 35, "production": 25},
    }
    _setup(monkeypatch, power)
    out = ph.nation_province_health(16, ROWS)
    # unpowered Gamma first, then lowest happiness (Beta), then Alpha
    assert [r["name"] for r in out["rows"]] == ["Gamma", "Beta", "Alpha"]
    assert out["unpowered"] == 1
    assert out["unstable"] == 1  # Beta (happiness 20); Gamma 70 is stable
    assert (out["power_used"], out["power_total"]) == (49, 42)
    assert (out["city_used"], out["city_total"]) == (7, 15)
    assert (out["land_used"], out["land_total"]) == (6, 15)
    gamma = out["rows"][0]
    assert (gamma["power_used"], gamma["power_total"], gamma["powered"]) == (35, 25, False)
    assert (gamma["city_used"], gamma["land_used"]) == (0, 0)  # no buildings row


def test_no_provinces_is_empty(monkeypatch):
    _setup(monkeypatch, {})
    out = ph.nation_province_health(16, [])
    assert out["rows"] == [] and out["unpowered"] == 0


def test_failure_never_breaks_the_overview(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    _setup(monkeypatch, {})
    monkeypatch.setattr(ph, "nation_province_power", boom)
    out = ph.nation_province_health(16, ROWS)
    assert out["rows"] == []
