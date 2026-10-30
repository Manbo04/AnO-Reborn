"""Safe Personal Deposit also binds the scheduled paths: recurring bank
trades and coalition bond-insurance payouts never dip into protected
members' personal balances."""
from app_core.coalitions import repositories
from app_core.game_ticks import bond_tick, recurring_bank_trades


class Cur:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.results.pop(0) if self.results else None

    def fetchall(self):
        return []


def test_bond_insurance_pays_only_unreserved_money(monkeypatch):
    monkeypatch.setattr(bond_tick, "_issuer_coalition", lambda db, uid: (7, []))
    monkeypatch.setattr(repositories, "protected_reserve_after", lambda db, c, r, *a, **k: 800)
    monkeypatch.setattr(bond_tick.ledger, "credit_gold", lambda db, uid, amt: None)
    cur = Cur([(1,), (1000,)])
    col, paid = bond_tick._apply_coalition_insurance(cur, 1, 2, 3, 5000)
    assert (col, paid) == (7, 200)
    assert any("money = money - %s" in s and p == (200, 7) for s, p in cur.calls)


def test_bond_insurance_pays_nothing_when_all_money_is_protected(monkeypatch):
    monkeypatch.setattr(bond_tick, "_issuer_coalition", lambda db, uid: (7, []))
    monkeypatch.setattr(repositories, "protected_reserve_after", lambda db, c, r, *a, **k: 5000)
    cur = Cur([(1,), (1000,)])
    assert bond_tick._apply_coalition_insurance(cur, 1, 2, 3, 5000) == (7, 0)
    assert not any("money = money - %s" in s for s, _ in cur.calls)


def test_recurring_trade_keeps_protected_reserve_in_vault(monkeypatch):
    from app_core.coalition_bank import services as bank

    monkeypatch.setattr(repositories, "protected_reserve_after", lambda db, c, r, *a, **k: 900)
    monkeypatch.setattr(bank, "get_role", lambda *a, **k: "member")
    monkeypatch.setattr(bank, "_take_from_player", lambda *a, **k: True)
    monkeypatch.setattr(bank, "get_officer_ids", lambda *a, **k: [])
    monkeypatch.setattr(bank, "_news", lambda *a, **k: None)
    import datetime as dt

    row = (7, 2, "iron", 10, "steel", 100, 24, 5, 0, 0, dt.datetime.now(dt.timezone.utc))
    # trade row, then the guarded vault UPDATE returns nothing (bank short), then run insert
    cur = Cur([row, None, (1,)])
    assert recurring_bank_trades._run_one(cur, 1) == "bank_short"
    upd = [p for s, p in cur.calls if s.startswith("UPDATE colBanks SET steel = steel - %s")]
    assert upd == [(100, 7, 1000)]
