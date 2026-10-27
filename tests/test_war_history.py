import pytest

from wars.history import record_building_loss

pytestmark = pytest.mark.no_server


class FakeDb:
    def __init__(self, war_row, fail_on_insert=False):
        self.war_row = war_row
        self.fail_on_insert = fail_on_insert
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if self.fail_on_insert and sql.startswith("INSERT"):
            raise RuntimeError("boom")

    def fetchone(self):
        return self.war_row


def test_records_against_active_war():
    db = FakeDb((7,))
    record_building_loss(db, 5, "farms", 3, "strike")
    inserts = [c for c in db.calls if c[0].startswith("INSERT")]
    assert inserts and inserts[0][1] == (7, 5, "farms", 3, "strike")


def test_no_war_no_row():
    db = FakeDb(None)
    record_building_loss(db, 5, "farms", 3, "strike")
    assert not [c for c in db.calls if c[0].startswith("INSERT")]


def test_zero_quantity_skipped():
    db = FakeDb((7,))
    record_building_loss(db, 5, "farms", 0, "strike")
    assert db.calls == []


def test_failure_never_raises_and_rolls_back():
    db = FakeDb((7,), fail_on_insert=True)
    record_building_loss(db, 5, "farms", 2, "strike")
    assert any("ROLLBACK TO SAVEPOINT" in c[0] for c in db.calls)
