from datetime import datetime, timezone

from app_core.economy import military_upkeep_v2 as v2


class FakeCursor:
    def __init__(self):
        self.q = 0
        self.description = None

    def execute(self, sql, params=None):
        self.q += 1
        if "user_military" in sql:
            self.description = [("user_id",), ("unit",), ("quantity",)]
            self.rows = [(1, "tanks", 2), (1, "soldiers", 10), (2, "tanks", 1)]
        else:
            self.description = [("resource_id",), ("name",)]
            self.rows = [(1, "rations"), (11, "steel"), (14, "gasoline"), (15, "ammunition")]

    def fetchall(self):
        return self.rows


def test_exact_spec_numbers():
    assert v2.UPKEEP_V2["soldiers"] == {"money": 75_000, "rations": 1}
    assert v2.UPKEEP_V2["aircraft_carriers"]["money"] == 5_000_000_000
    assert v2.UPKEEP_V2["cruisers"] == {"gasoline": 20, "ammunition": 15, "steel": 20, "money": 2_000_000_000}


def test_rows_aggregate_per_user():
    rows = {(r["user_id"], r["resource"]): r for r in v2.v2_rows(FakeCursor())}
    assert rows[(1, "money")]["required_amount"] == 2 * 45_000_000 + 10 * 75_000
    assert rows[(1, "money")]["resource_id"] is None
    assert rows[(1, "steel")]["required_amount"] == 4
    assert rows[(1, "rations")]["required_amount"] == 10
    assert rows[(2, "gasoline")]["resource_id"] == 14


def test_grace_period():
    before = datetime(2026, 11, 6, 18, 59, tzinfo=timezone.utc)
    assert not v2.v2_active(before)
    assert v2.v2_active(v2.UPKEEP_V2_START)
