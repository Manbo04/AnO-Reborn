import pytest
from units import Units


class DummyUnits:
    # Provide a small, deterministic set of available units for tests
    @staticmethod
    def get_military(user_id):
        return {"soldiers": 1000, "tanks": 50, "artillery": 20}

    @staticmethod
    def get_special(user_id):
        return {}


@pytest.fixture(autouse=True)
def monkey_units(monkeypatch):
    # Monkeypatch Units' DB-dependent getters to use static values
    monkeypatch.setattr(Units, "get_military", DummyUnits.get_military)
    monkeypatch.setattr(Units, "get_special", DummyUnits.get_special)


def test_attach_three_unit_types_zero_amount_allowed():
    u = Units(16)
    # Simulate selecting three different unit types (amounts 0 at selection stage)
    selected = {"soldiers": 0, "tanks": 0, "artillery": 0}
    err = u.attach_units(selected, 3)
    assert err is None
    assert u.selected_units_list == ["soldiers", "tanks", "artillery"]


def test_attach_rejects_missing_unit_type():
    u = Units(16)
    # Missing one selection (None key) should be rejected
    selected = {"soldiers": 0, None: 0}
    err = u.attach_units(selected, 3)
    assert err == "Not enough unit type selected"


def test_attach_checks_amounts_when_nonzero():
    u = Units(16)
    # Provide amounts larger than available -> invalid
    selected = {"soldiers": 2000, "tanks": 0, "artillery": 0}
    err = u.attach_units(selected, 3)
    assert err == "Invalid amount selected!"
