"""Nuke rework phase 1: flag gating, capacity-capped production, no banking."""
from decimal import Decimal

from app_core import nuke_rework as nr
from app_core.game_ticks import nuke_production as np_


class FakeDB:
    def __init__(self, owned=0, stocked=0, silos=2, progress=0, stock=None):
        self.owned, self.stocked, self.silos, self.progress = owned, stocked, silos, progress
        self.stock = stock if stock is not None else {r: 10**9 for r in nr.MISSILE_RESOURCES}
        self.rows, self.deltas, self.saved, self.stock_added = [], [], None, 0

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        if "FROM user_nuke_progress" in s:
            self.rows = [(self.progress,)] if self.progress is not None else []
        elif "FROM user_military" in s:
            self.rows = [(self.owned,)]
        elif "FROM user_unit_stockpile" in s:
            self.rows = [(self.stocked,)]
        elif "bd.name='silos'" in s:
            self.rows = [(self.silos,)]
        elif "FROM resource_dictionary rd" in s:
            self.rows = list(self.stock.items())
        elif s.startswith("INSERT INTO user_unit_stockpile"):
            self.stock_added = params[2]
            self.rows = []
        elif s.startswith("INSERT INTO user_nuke_progress"):
            self.saved = params[1]
            self.rows = []
        elif "FROM user_nuke_settings" in s:
            self.rows = []
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


RID = {r: i for i, r in enumerate(nr.MISSILE_RESOURCES)}


def _patch_ledger(monkeypatch, db):
    monkeypatch.setattr(np_.ledger, "ensure_resource_rows_batch", lambda *a, **k: None)
    monkeypatch.setattr(np_.ledger, "adjust_resource_batch", lambda d, rows, **k: db.deltas.extend(rows))


def test_hidden_when_flag_off(monkeypatch):
    monkeypatch.setattr(nr, "is_on", lambda *a, **k: False)
    assert nr.is_hidden(nr.FACILITY) and not nr.activatable("nukes", 1)
    from app_core.economy import ledger_goods
    assert nr.FACILITY not in ledger_goods.visible([nr.FACILITY, "farms"])


def test_visible_when_flag_on(monkeypatch):
    monkeypatch.setattr(nr, "is_on", lambda *a, **k: True)
    assert not nr.is_hidden(nr.FACILITY) and nr.activatable("nukes", 1)
    assert not nr.activatable("icbms", 1)


def test_one_facility_needs_72_hours(monkeypatch):
    db = FakeDB(progress=Decimal("0.9862"))  # 71/72
    _patch_ledger(monkeypatch, db)
    assert np_.produce_for_user(db, 1, 1, 7, RID) == 1
    assert db.stock_added == 1
    assert db.saved < Decimal("0.02")
    assert len(db.deltas) == len(nr.MISSILE_RESOURCES)
    assert all(d[2] < 0 for d in db.deltas)


def test_partial_progress_makes_nothing(monkeypatch):
    db = FakeDB(progress=Decimal(0))
    _patch_ledger(monkeypatch, db)
    assert np_.produce_for_user(db, 1, 1, 7, RID) == 0
    assert db.stock_added == 0 and db.deltas == []


def test_silo_capacity_caps_and_does_not_bank(monkeypatch):
    db = FakeDB(owned=1, stocked=1, silos=2, progress=Decimal(5))
    _patch_ledger(monkeypatch, db)
    assert np_.produce_for_user(db, 1, 3, 7, RID) == 0  # full: 1 owned + 1 stocked = 2 silos
    assert db.saved == Decimal(1)  # progress capped, no banking


def test_unaffordable_makes_nothing_and_spends_nothing(monkeypatch):
    db = FakeDB(progress=Decimal(1), stock={r: 0 for r in nr.MISSILE_RESOURCES})
    _patch_ledger(monkeypatch, db)
    assert np_.produce_for_user(db, 1, 1, 7, RID) == 0
    assert db.deltas == [] and db.saved == Decimal(1)


def test_building_registered_everywhere():
    import variables
    n = nr.FACILITY
    assert f"{n}_price" in variables.PROVINCE_UNIT_PRICES and f"{n}_resource" in variables.PROVINCE_UNIT_PRICES
