"""Ledger goods: master flag gating, cement cost, wear-out, goods use, migrations.

Everything here must hold with the flags OFF (the shipped default): no cost,
no consumption, nothing visible, nothing buildable, nothing tradable.
"""
import glob
import math
import os
from unittest import mock

import pytest

import variables
from app_core.economy import building_costs, goods_use, ledger_goods, wearout
from app_core.economy.ledger_goods import LEDGER_BUILDINGS, LEDGER_RESOURCES

pytestmark = pytest.mark.no_server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _flags(*on):
    """Patch feature_flags.is_on everywhere so only the flags in ``on`` are on."""
    fake = lambda key, user_id=None, default=False: key in on  # noqa: E731
    return mock.patch.multiple(
        "app_core.feature_flags", is_on=mock.DEFAULT
    ), fake


class _Flags:
    def __init__(self, *on):
        self.on = set(on)
        self._patches = []

    def _fake(self, key, user_id=None, default=False):
        return key in self.on

    def __enter__(self):
        for target in (
            "app_core.feature_flags.is_on",
            "app_core.economy.ledger_goods.is_on",
            "app_core.economy.wearout.is_on",
            "app_core.economy.goods_use.is_on",
        ):
            p = mock.patch(target, side_effect=self._fake)
            p.start()
            self._patches.append(p)
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class _Cursor:
    """Minimal cursor: answers queries by substring, records writes."""

    def __init__(self, answers):
        self.answers = answers
        self.executed = []
        self.many = []
        self._last = None

    def execute(self, sql, args=None):
        self.executed.append(sql)
        self._last = next((v for k, v in self.answers if k in sql and (not callable(v) or True)), [])
        if callable(self._last):
            self._last = self._last(args)

    def fetchone(self):
        return self._last[0] if self._last else None

    def fetchall(self):
        return list(self._last or [])

    def executemany(self, sql, rows):
        self.many.append((sql, list(rows)))


# --- catalogue consistency -------------------------------------------------


def test_every_ledger_good_and_building_is_fully_defined():
    assert len(LEDGER_RESOURCES) == 11 and len(LEDGER_BUILDINGS) == 11
    for res in LEDGER_RESOURCES:
        assert res in variables.RESOURCES
    produced = set()
    for b in LEDGER_BUILDINGS:
        assert b in variables.BUILDINGS
        assert f"{b}_price" in variables.PROVINCE_UNIT_PRICES
        infra = variables.NEW_INFRA[b]
        assert infra.get("plus"), b
        produced.update(infra["plus"])
        # a producer never consumes its own output (no free loop)
        minus = infra.get("minus") or {}
        assert not (set(minus) & set(infra["plus"])), b
    assert produced == set(LEDGER_RESOURCES)


def test_every_ledger_good_and_building_has_an_image_file():
    # Placeholders reuse existing game images until real art is sourced.
    import game_ui

    for key, table in [(b, game_ui.BUILDING_LEGACY_IMAGES) for b in LEDGER_BUILDINGS] + [
        (r, game_ui.RESOURCE_LEGACY_IMAGES) for r in LEDGER_RESOURCES
    ]:
        rel = table[key]
        assert os.path.isfile(os.path.join(ROOT, "static", "images", rel)), rel


# --- master flag -------------------------------------------------------------


def test_flag_off_hides_goods_and_buildings():
    with _Flags():
        assert ledger_goods.is_hidden("cement") and ledger_goods.is_hidden("cement_works")
        assert not ledger_goods.is_hidden("steel")
        shown = ledger_goods.visible(variables.RESOURCES)
        assert not (set(shown) & set(LEDGER_RESOURCES))
        assert "steel" in shown and "rations" in shown


def test_flag_on_shows_everything():
    with _Flags("ledger_goods"):
        assert not ledger_goods.is_hidden("cement")
        assert ledger_goods.visible(variables.RESOURCES) == list(variables.RESOURCES)


def test_flag_off_building_cannot_be_bought():
    from app_core.economy.building_purchase import BuildingPurchaseError, purchase_building

    db = mock.Mock()
    with _Flags():
        with pytest.raises(BuildingPurchaseError):
            purchase_building(db, 16, 101, "cement_works", 1)
    db.execute.assert_not_called()  # rejected before any query or lock


def test_flag_off_goods_are_not_tradable():
    from app_core.market import repositories

    db = mock.Mock()
    with _Flags():
        assert repositories.is_active_resource(db, "cement") is False
    db.execute.assert_not_called()


def test_flag_off_quick_build_sheet_has_no_ledger_buildings():
    import game_ui

    with _Flags():
        payload = game_ui.build_province_layout_payload({"id": 1}, {})
    assert not (set(LEDGER_BUILDINGS) & set(_names(payload)))


def _names(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _names(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _names(v)
    elif isinstance(obj, str):
        yield obj


# --- cement ------------------------------------------------------------------


def test_cement_cost_off_by_default():
    with _Flags():
        assert building_costs.ledger_cement_cost("steel_mills", 9_000_000) == {}
        assert "cement" not in building_costs.get_build_cost("steel_mills")["resources"]


def test_cement_cost_needs_the_master_flag_too():
    with _Flags("ledger_cement"):
        assert building_costs.ledger_cement_cost("steel_mills", 9_000_000) == {}


def test_cement_cost_one_per_100k_gold_min_one():
    with _Flags("ledger_goods", "ledger_cement"):
        assert building_costs.ledger_cement_cost("steel_mills", 9_000_000) == {"cement": 90}
        assert building_costs.ledger_cement_cost("steel_mills", 149_999) == {"cement": 1}
        assert building_costs.ledger_cement_cost("steel_mills", 50) == {"cement": 1}
        # the cement producer itself is exempt, so the chain can always be started
        assert building_costs.ledger_cement_cost("cement_works", 9_000_000) == {}
        assert building_costs.ledger_cement_cost("not_a_building", 9_000_000) == {}


def test_cement_is_not_part_of_the_sell_refund():
    # Sell refunds come from PROVINCE_UNIT_PRICES, which never lists cement,
    # so buy -> sell cannot mint or return cement.
    for key, cost in variables.PROVINCE_UNIT_PRICES.items():
        if key.endswith("_resource"):
            assert "cement" not in (cost or {}), key


# --- wear-out ----------------------------------------------------------------


def test_wearout_exempts_food_buildings():
    worn = wearout.worn_buildings()
    assert "farms" not in worn and "fisheries" not in worn
    assert "steel_mills" in worn


def test_wearout_off_touches_nothing():
    cur = _Cursor([])
    deltas = {}
    with _Flags():
        assert wearout.apply(cur, [1, 2], {}, deltas) == {}
    with _Flags("ledger_wearout"):  # sub-flag alone is not enough
        assert wearout.apply(cur, [1, 2], {}, deltas) == {}
    assert cur.executed == [] and deltas == {}


def test_wearout_math_full_ramp():
    cur = _Cursor(
        [
            ("ledger_wear_meta", [(wearout.RAMP_HOURS,)]),
            ("user_buildings", [(1, 500), (2, 500), (3, 0)]),
        ]
    )
    stock = {1: {"machinery": 100}, 2: {"machinery": 4}, 3: {"machinery": 0}}
    deltas = {}
    with _Flags("ledger_goods", "ledger_wearout"):
        factors = wearout.apply(cur, [1, 2, 3], stock, deltas)
    need = math.ceil(500 / wearout.BUILDINGS_PER_MACHINERY)
    assert need == 10
    assert factors[1] == 1.0 and deltas[1]["machinery"] == -10
    assert factors[2] == pytest.approx(0.5 + 0.5 * 0.4) and deltas[2]["machinery"] == -4
    assert factors[3] == 1.0 and 3 not in deltas  # no industry, nothing to wear
    assert all(wearout.FLOOR <= f <= 1.0 for f in factors.values())


def test_wearout_never_takes_more_than_stock():
    cur = _Cursor([("ledger_wear_meta", [(10**6,)]), ("user_buildings", [(1, 10**6)])])
    deltas = {}
    with _Flags("ledger_goods", "ledger_wearout"):
        factors = wearout.apply(cur, [1], {1: {"machinery": 7}}, deltas)
    assert deltas[1]["machinery"] == -7
    assert factors[1] >= wearout.FLOOR


# --- goods use ---------------------------------------------------------------


def _goods_cursor(pop, farms, hospitals, ticks=goods_use.RAMP_HOURS):
    def buildings(args):
        name = args[1]
        return [(1, farms)] if name == "farms" else [(1, hospitals)]

    return _Cursor(
        [
            ("ledger_goods_meta", [(ticks,)]),
            ("FROM provinces", [(1, pop)]),
            ("user_buildings", buildings),
        ]
    )


def test_goods_use_off_touches_nothing():
    cur = _Cursor([])
    deltas = {}
    with _Flags():
        assert goods_use.apply(cur, [1], {}, deltas) == {"farm": {}, "happy": {}}
    with _Flags("ledger_goods_use"):
        assert goods_use.apply(cur, [1], {}, deltas) == {"farm": {}, "happy": {}}
    assert cur.executed == [] and deltas == {}


def test_goods_use_fully_supplied_nation():
    pop, farms, hospitals = 10_000_000, 40, 5
    have = {1: {"clothing": 10**6, "medicine": 10**6, "fertilizer": 10**6, "electronics": 10**6, "vehicles": 10**6, "luxury_goods": 10**6}}
    deltas = {}
    with _Flags("ledger_goods", "ledger_goods_use"):
        out = goods_use.apply(_goods_cursor(pop, farms, hospitals), [1], have, deltas)
    assert deltas[1]["clothing"] == -math.ceil(pop / goods_use.CLOTHING_POP)
    assert deltas[1]["medicine"] == -hospitals * goods_use.MED_PER_HOSPITAL
    assert deltas[1]["fertilizer"] == -farms * goods_use.FERT_PER_FARM
    for g in goods_use.PROSPERITY:
        assert deltas[1][g] == -math.ceil(pop / goods_use.PROSP_POP)
    assert out["farm"][1] == pytest.approx(1 + goods_use.FERT_BONUS)
    assert out["happy"][1] == pytest.approx(goods_use.PROSP_BONUS)


def test_goods_use_empty_nation_is_bounded_and_uses_nothing():
    deltas = {}
    with _Flags("ledger_goods", "ledger_goods_use"):
        out = goods_use.apply(_goods_cursor(10_000_000, 40, 5), [1], {1: {}}, deltas)
    assert not any(deltas.get(1, {}).values())  # nothing to take, never negative
    assert out["farm"][1] == 1.0  # no fertilizer = no bonus, never a penalty
    assert out["happy"][1] == pytest.approx(-(goods_use.CLOTHING_PEN + goods_use.MED_PEN))


def test_goods_use_ramp_softens_the_first_tick():
    deltas = {}
    with _Flags("ledger_goods", "ledger_goods_use"):
        out = goods_use.apply(_goods_cursor(10_000_000, 0, 0, ticks=0), [1], {1: {}}, deltas)
    assert out["happy"][1] == pytest.approx(-goods_use.CLOTHING_PEN * goods_use.RAMP_START)


# --- migrations --------------------------------------------------------------

LEDGER_MIGRATIONS = [
    "20261108_1900_machinery.sql",
    "20261114_1000_atlas_goods.sql",
    "20261114_1100_goods_use.sql",
    "20261114_1200_ledger_goods_flag.sql",
]


def test_ledger_migrations_exist_and_only_add():
    names = {os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "migrations", "*.sql"))}
    for name in LEDGER_MIGRATIONS:
        assert name in names
        sql = open(os.path.join(ROOT, "migrations", name)).read().upper()
        for bad in ("DROP ", "TRUNCATE", "DELETE FROM", "TRUE, 100"):
            assert bad not in sql, f"{name}: {bad}"
        assert "UPDATE USER_ECONOMY" not in sql and "UPDATE STATS" not in sql


def test_ledger_migrations_are_idempotent_and_leave_flags_off():
    from database import get_db_connection

    ctx = get_db_connection()
    conn = ctx.__enter__()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, enabled FROM feature_flags WHERE key LIKE 'ledger_%%'")
        before = dict(cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM resource_dictionary")
        n_res = cur.fetchone()[0]
        conn.commit()
        for _ in range(2):  # running them again must change nothing
            for name in LEDGER_MIGRATIONS:
                cur.execute(open(os.path.join(ROOT, "migrations", name)).read())
                conn.commit()
        cur.execute("SELECT key, enabled FROM feature_flags WHERE key LIKE 'ledger_%%'")
        after = dict(cur.fetchall())
        for key in ("ledger_goods", "ledger_cement", "ledger_wearout", "ledger_goods_use"):
            assert key in after
            assert after[key] == before.get(key, False), f"{key} flipped by a re-run"
        cur.execute("SELECT COUNT(*) FROM resource_dictionary")
        assert cur.fetchone()[0] == max(n_res, cur.rowcount and n_res)
        cur.execute("SELECT COUNT(*) FROM resource_dictionary WHERE name = ANY(%s)", (list(LEDGER_RESOURCES),))
        assert cur.fetchone()[0] == 11
        cur.execute("SELECT COUNT(*) FROM building_dictionary WHERE name = ANY(%s)", (list(LEDGER_BUILDINGS),))
        assert cur.fetchone()[0] == 11
        conn.commit()
    finally:
        ctx.__exit__(None, None, None)


def test_fresh_schema_ships_every_ledger_flag_off():
    from database import get_db_connection

    ctx = get_db_connection()
    conn = ctx.__enter__()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key FROM feature_flags WHERE key LIKE 'ledger_%%' AND enabled")
        on = [r[0] for r in cur.fetchall()]
        conn.commit()
    finally:
        ctx.__exit__(None, None, None)
    if os.environ.get("CI") or "55432" in os.environ.get("DATABASE_URL", ""):
        assert on == [], f"ledger flags must ship OFF, found on: {on}"
