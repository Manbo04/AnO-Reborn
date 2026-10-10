"""Regressions from the 2026-10-10 Discord sweep: strikes and Iron Dome
dismantles wrote negative quantities, which the tables' quantity >= 0
checks reject (players got a 500)."""


class _Cursor:
    def __init__(self, rows=None, one=None):
        self.rows = rows or []
        self.one = one
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


def test_building_damage_spreads_over_province_rows():
    from wars.service import apply_building_damage

    # user_buildings is one row per province: (province_id, quantity, building_id)
    db = _Cursor(rows=[(10, 5, 4), (11, 2, 4), (12, 1, 4)])
    destroyed, had = apply_building_damage(db, 99, "steel_mills", damage_points=70, threshold=10)
    assert (destroyed, had) == (7, True)
    updates = [p for s, p in db.sql if s.startswith("UPDATE user_buildings")]
    # 5 from the biggest stack, then 2; every UPDATE is filtered by province
    # and never takes more than that row holds.
    assert updates == [(5, 99, 4, 10), (2, 99, 4, 11)]


def test_building_damage_caps_at_total_owned():
    from wars.service import apply_building_damage

    db = _Cursor(rows=[(10, 1, 4), (11, 1, 4)])
    destroyed, _ = apply_building_damage(db, 99, "silos", damage_points=10_000, threshold=15)
    assert destroyed == 2


def test_building_damage_none_owned():
    from wars.service import apply_building_damage

    assert apply_building_damage(_Cursor(rows=[]), 99, "silos", 100, 15) == (0, False)


def test_dome_dismantle_updates_instead_of_negative_upsert(monkeypatch):
    import app_core.military.iron_dome as dome

    db = _Cursor(one=(7,))  # owner id 7 and also current dome count below
    monkeypatch.setattr(dome, "province_domes", lambda db, pid: 1)
    paid = {}
    monkeypatch.setattr(
        dome, "update_manpower_and_gold",
        lambda db, uid, gold_delta, manpower_delta: paid.update(gold=gold_delta),
    )
    ok, _ = dome.change_domes(db, 7, 2288, "sell", 1)
    assert ok
    assert paid["gold"] == int(dome.DOME_GOLD_COST * dome.SELL_REFUND)
    assert not any(s.startswith("INSERT INTO province_iron_domes") for s, _ in db.sql)
    assert ("UPDATE province_iron_domes SET quantity = quantity - %s WHERE province_id = %s", (1, 2288)) in db.sql


def test_dome_dismantle_more_than_owned_refused(monkeypatch):
    import app_core.military.iron_dome as dome

    monkeypatch.setattr(dome, "province_domes", lambda db, pid: 1)
    ok, msg = dome.change_domes(_Cursor(one=(7,)), 7, 2288, "sell", 2)
    assert not ok and "only have 1" in msg
