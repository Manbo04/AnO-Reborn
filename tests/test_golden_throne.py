"""The Golden Throne: vitality math, dawn tick, pilgrim limits, modifiers. DB-free."""
import random
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app_core.traits import golden_throne as gt
from app_core.traits import golden_throne_config as C
from app_core.traits import modifiers, registry
from tests._fake_db import FakeCursor

pytestmark = pytest.mark.no_server
ROOT = Path(__file__).resolve().parent.parent

# 2026-11-03 06:30 UTC == 08:30 in Vilnius (UTC+2): after dawn (06:00 local).
AFTER_DAWN = datetime(2026, 11, 3, 6, 30, tzinfo=timezone.utc)
BEFORE_DAWN = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)  # 04:00 local


# ---------------------------------------------------------------- vitality math
@pytest.mark.parametrize(
    "weight,sacrificed,crisis,expected",
    [
        (0, True, False, -1.0),    # nobody comes: -4 + 3
        (2, True, False, 0.0),     # two pilgrims hold it steady (break-even)
        (6, True, False, 2.0),
        (10, True, False, 4.0),    # ten pilgrims: +4/day
        (25, True, False, 4.0),    # capped at 10 weight
        (0, False, False, -7.0),   # skipped: -4 - 3, no pilgrim credit
        (5, False, False, -7.0),
        (0, True, True, 3.0),      # crisis: decay paused, +3
        (4, True, True, 5.0),
    ],
)
def test_vitality_delta(weight, sacrificed, crisis, expected):
    assert gt.vitality_delta(weight, sacrificed, crisis) == pytest.approx(expected)


def test_vitality_is_clamped():
    assert gt.clamp_vitality(150) == 100.0
    assert gt.clamp_vitality(-9) == 0.0


def test_no_pilgrims_takes_about_sixty_days_to_empty():
    v, days = C.START_VITALITY, 0
    while v > 0:
        v = gt.clamp_vitality(v + gt.vitality_delta(0, True, False))
        days += 1
    assert 55 <= days <= 65


@pytest.mark.parametrize(
    "v,crisis,key",
    [(100, False, "blazing"), (80, False, "blazing"), (79.9, False, "steady"),
     (40, False, "steady"), (39, False, "flickering"), (15, False, "flickering"),
     (14, False, "failing"), (1, False, "failing"), (0, True, "crisis"), (0, False, "crisis")],
)
def test_tiers(v, crisis, key):
    assert gt.tier_for(v, crisis)["key"] == key


def test_bonuses_stay_small():
    for t in C.TIERS:
        assert abs(t[3]) <= 5 and abs(t[4]) <= 5
    assert max(t[3] for t in C.TIERS) <= 3.0
    assert C.PILGRIM_BLESSING_PCT <= 2.0


def test_crisis_enters_at_zero_and_exits_with_hysteresis():
    assert gt.next_crisis(False, 0.0) is True
    assert gt.next_crisis(False, 5.0) is False
    assert gt.next_crisis(True, 19.9) is True    # still in crisis below 20
    assert gt.next_crisis(True, 20.0) is False


@pytest.mark.parametrize("weight,pilgrims,own", [(0, 0, 10), (3, 3, 7), (10, 10, 0), (40, 10, 0)])
def test_pilgrims_offset_the_sacrifice_first(weight, pilgrims, own):
    assert gt.split_souls(weight) == (pilgrims, own)


# ---------------------------------------------------------------- dawn dates (Vilnius)
def test_dawn_boundaries():
    assert gt.next_dawn_date(BEFORE_DAWN) == date(2026, 11, 3)   # 04:00 local -> today's dawn
    assert gt.next_dawn_date(AFTER_DAWN) == date(2026, 11, 4)    # 08:30 local -> tomorrow's
    assert gt.due_dawn(None, BEFORE_DAWN) is None
    assert gt.due_dawn(None, AFTER_DAWN) == date(2026, 11, 3)
    assert gt.due_dawn(date(2026, 11, 3), AFTER_DAWN) is None    # already ran today
    assert gt.due_dawn(date(2026, 10, 20), AFTER_DAWN) == date(2026, 11, 3)  # missed days skipped


def test_vigil_day_counts_from_one():
    assert gt.vigil_day(date(2026, 11, 3), AFTER_DAWN) == 1
    assert gt.vigil_day(date(2026, 11, 1), AFTER_DAWN) == 3


def test_surge_doubles_pilgrim_weight_only_while_active():
    later = AFTER_DAWN + timedelta(hours=5)
    assert gt.pilgrim_weight_now("surge", later, AFTER_DAWN) == C.SURGE_MULTIPLIER
    assert gt.pilgrim_weight_now("surge", AFTER_DAWN - timedelta(hours=1), AFTER_DAWN) == 1
    assert gt.pilgrim_weight_now("heretics", later, AFTER_DAWN) == 1
    assert gt.pilgrim_weight_now(None, None, AFTER_DAWN) == 1


def test_events_are_rare_and_spaced():
    today = date(2026, 11, 3)
    assert gt.roll_event(random.Random(1), today - timedelta(days=2), today) is None
    rng = random.Random(7)
    hits = sum(1 for _ in range(7000) if gt.roll_event(rng, None, today))
    assert 700 <= hits <= 1300  # about 1 in 7


# ---------------------------------------------------------------- the dawn tick
def _dawn_cursor(last_dawn=None, conflict=False, weight=3, pop=5_000_000, vitality=60.0, crisis=False):
    return FakeCursor([
        ("FROM throne_state WHERE user_id", [(vitality, last_dawn, crisis, None, None, None, 100)]),
        ("INSERT INTO throne_days", [] if conflict else [(date(2026, 11, 3),)]),
        ("FROM throne_pilgrimages WHERE for_dawn", [(weight, weight)]),
        ("COALESCE(SUM(population)", [(pop,)]),
        ("SELECT id, population FROM provinces", [(1, 3_000_000), (2, 2_000_000)]),
    ])


def _no_event(monkeypatch):
    monkeypatch.setattr(gt, "roll_event", lambda *a, **k: None)


def test_dawn_runs_the_sacrifice(monkeypatch):
    _no_event(monkeypatch)
    cur = _dawn_cursor(weight=3)
    out = gt.run_dawn(cur, 1, now=AFTER_DAWN)
    assert out["day"] == date(2026, 11, 3) and out["souls"] == 10 and not out["skipped"]
    assert out["vitality"] == pytest.approx(60.5)  # -4 + 3 + 0.5*3
    taken = [p for s, p in cur.executed if s.startswith("UPDATE provinces")]
    assert taken and taken[0][0] == 7  # 10 souls - 3 from pilgrims come from the nation
    state = [p for s, p in cur.executed if s.startswith("UPDATE throne_state")][0]
    assert state[0] == pytest.approx(60.5) and state[3] == 110  # souls_total 100 + 10


def test_dawn_is_idempotent(monkeypatch):
    _no_event(monkeypatch)
    # already ran today -> nothing happens, nothing written
    cur = _dawn_cursor(last_dawn=date(2026, 11, 3))
    assert gt.run_dawn(cur, 1, now=AFTER_DAWN) is None
    assert not any(s.startswith(("UPDATE", "INSERT")) for s in cur.sql_log())
    # a second worker loses the throne_days primary-key race -> nothing happens
    cur = _dawn_cursor(conflict=True)
    assert gt.run_dawn(cur, 1, now=AFTER_DAWN) is None
    assert not any(s.startswith("UPDATE") for s in cur.sql_log())


def test_dawn_not_due_before_six(monkeypatch):
    _no_event(monkeypatch)
    cur = _dawn_cursor()
    assert gt.run_dawn(cur, 1, now=BEFORE_DAWN) is None


def test_low_population_skips_sacrifice_and_hurts_vitality(monkeypatch):
    _no_event(monkeypatch)
    cur = _dawn_cursor(weight=0, pop=50_000)
    out = gt.run_dawn(cur, 1, now=AFTER_DAWN)
    assert out["skipped"] and out["souls"] == 0
    assert out["vitality"] == pytest.approx(53.0)  # 60 - 4 - 3
    assert not any(s.startswith("UPDATE provinces") for s in cur.sql_log())


def test_crisis_begins_at_zero_and_recovers(monkeypatch):
    _no_event(monkeypatch)
    out = gt.run_dawn(_dawn_cursor(weight=0, vitality=2.0, pop=50_000), 1, now=AFTER_DAWN)
    assert out["vitality"] == 0.0 and out["crisis"] and out["tier"] == "crisis"
    out = gt.run_dawn(_dawn_cursor(weight=0, vitality=0.0, crisis=True), 1, now=AFTER_DAWN)
    assert out["vitality"] == pytest.approx(3.0) and out["crisis"]  # decay paused, +3


# ---------------------------------------------------------------- pilgrims
def _pilgrim_cursor(owner=1, auth=None, joined="2026-01-01", conflict=False):
    return FakeCursor([
        ("SELECT user_id FROM nation_traits", [(owner,)]),
        ("SELECT auth_type, date FROM users", [(auth, joined)]),
        ("SELECT active_event, event_ends_at FROM throne_state", [(None, None)]),
        ("INSERT INTO throne_pilgrimages", [] if conflict else [(1,)]),
    ])


def _paid(monkeypatch, pop_ok=True):
    monkeypatch.setattr(gt, "take_population", lambda db, uid, n: n if pop_ok else 0)


def test_pilgrimage_success_takes_people_blesses_and_logs(monkeypatch):
    _paid(monkeypatch)
    cur = _pilgrim_cursor()
    ok, msg = gt.send_pilgrims(cur, 5, now=AFTER_DAWN)
    assert ok and "blesses" in msg
    people = [p for s, p in cur.executed if s.startswith("UPDATE throne_pilgrimages SET people")][0]
    assert people[0] == C.PILGRIM_COST_POPULATION  # the Wall records how many people were given
    log = cur.sql_log()
    assert any("INSERT INTO throne_blessings" in s and "DO UPDATE" in s for s in log)
    assert "RELEASE SAVEPOINT throne_pilgrimage" in log
    blessing = [p for s, p in cur.executed if "INSERT INTO throne_blessings" in s][0]
    assert blessing[1] == AFTER_DAWN + timedelta(hours=24) and blessing[2] == 2.0  # refreshed, not stacked


def test_pilgrimage_once_per_window(monkeypatch):
    _paid(monkeypatch)
    cur = _pilgrim_cursor(conflict=True)  # the UNIQUE row already exists
    ok, msg = gt.send_pilgrims(cur, 5, now=AFTER_DAWN)
    assert not ok and msg == gt.PILGRIM_MESSAGES["already"]
    assert "ROLLBACK TO SAVEPOINT throne_pilgrimage" in cur.sql_log()
    assert not any("throne_blessings" in s for s in cur.sql_log())


def test_pilgrimage_key_is_dawn_and_user(monkeypatch):
    _paid(monkeypatch)
    cur = _pilgrim_cursor()
    gt.send_pilgrims(cur, 5, now=AFTER_DAWN)
    ins = [p for s, p in cur.executed if "INSERT INTO throne_pilgrimages" in s][0]
    assert ins[0] == date(2026, 11, 4) and ins[1] == 5  # tomorrow's dawn, this nation
    src = (ROOT / "migrations").glob("*nation_traits_golden_throne.sql")
    assert "UNIQUE (for_dawn, pilgrim_user_id)" in next(src).read_text()


def test_unaffordable_pilgrimage_does_not_burn_the_daily_slot(monkeypatch):
    _paid(monkeypatch, pop_ok=False)
    cur = _pilgrim_cursor()
    ok, msg = gt.send_pilgrims(cur, 5, now=AFTER_DAWN)
    assert not ok and msg == gt.PILGRIM_MESSAGES["pop"]
    assert "ROLLBACK TO SAVEPOINT throne_pilgrimage" in cur.sql_log()  # row undone
    assert not any("throne_blessings" in s for s in cur.sql_log())


@pytest.mark.parametrize(
    "uid,kwargs,key",
    [(1, {}, "self"),                      # can't pilgrim yourself
     (5, {"auth": "bot"}, "bot"),
     (5, {"joined": "2026-11-02"}, "young")],
)
def test_pilgrimage_refusals_touch_nothing(monkeypatch, uid, kwargs, key):
    _paid(monkeypatch)
    cur = _pilgrim_cursor(**kwargs)
    ok, msg = gt.send_pilgrims(cur, uid, now=AFTER_DAWN)
    assert not ok and msg == gt.PILGRIM_MESSAGES[key]
    assert not any(s.startswith(("INSERT", "UPDATE")) for s in cur.sql_log())


def test_pilgrimage_needs_an_active_throne(monkeypatch):
    _paid(monkeypatch)
    cur = FakeCursor([])  # no owner row
    ok, msg = gt.send_pilgrims(cur, 5, now=AFTER_DAWN)
    assert not ok and msg == gt.PILGRIM_MESSAGES["noowner"]


# ---------------------------------------------------------------- modifiers
def test_holder_modifiers_hive_tradeoffs_and_events():
    m = gt.holder_modifiers((90, False, None, None), now=AFTER_DAWN)
    assert m["pop_cap_mult"] == C.HIVE_POP_CAP_MULT and m["industry_mult"] == C.HIVE_INDUSTRY_MULT
    assert m["food_mult"] == C.HIVE_FOOD_MULT < 1 and m["upkeep_mult"] == C.HIVE_UPKEEP_MULT > 1
    assert m["happiness_pct"] == 3.0 and m["defense_pct"] == 5.0
    live = AFTER_DAWN + timedelta(hours=3)
    assert gt.holder_modifiers((90, False, "heretics", live), now=AFTER_DAWN)["happiness_pct"] == -2.0
    assert gt.holder_modifiers((90, False, "heretics", AFTER_DAWN - timedelta(hours=1)), now=AFTER_DAWN)["happiness_pct"] == 3.0
    crisis = gt.holder_modifiers((0, True, None, None), now=AFTER_DAWN)
    assert crisis["happiness_pct"] == -10.0 and crisis["defense_pct"] == -10.0


def test_load_all_blessing_and_holder_only():
    cur = FakeCursor([
        ("FROM throne_state s JOIN nation_traits", [(1, 90, False, None, None)]),
        ("FROM throne_blessings", [(7, 2.0), (1, 2.0)]),
    ])
    mods = modifiers.load_all(cur)
    assert set(mods) == {1, 7}
    assert mods[7]["happiness_pct"] == 2.0 and mods[7]["food_mult"] == 1.0  # blessing only
    assert mods[1]["happiness_pct"] == 5.0  # tier +3 and a blessing +2
    assert 5 not in mods  # ordinary nations are absent: zero cost, zero effect


def test_load_all_survives_missing_tables_and_kill_switch(monkeypatch):
    class Boom(FakeCursor):
        def execute(self, sql, params=None):
            if "throne_state" in sql:
                raise RuntimeError("relation does not exist")
            super().execute(sql, params)

    assert modifiers.load_all(Boom()) == {}
    monkeypatch.setenv("NATION_TRAITS_DISABLED", "1")
    assert modifiers.load_all(FakeCursor()) == {}


def test_population_sim_uses_level_modifiers(monkeypatch):
    from app_core.game_ticks import population2

    seen = {}
    monkeypatch.setattr(population2, "homes", lambda *a, **k: 100)

    def fake_step(p, hospitals, home_count, *a, **k):
        seen["homes"], seen["happiness"] = home_count, p["happiness"]
        return 0, 0, 0

    monkeypatch.setattr(population2, "step_province", fake_step)
    monkeypatch.setattr(population2, "distribute_migration", lambda *a, **k: {})
    prov = {"id": 1, "population": 1000, "pop_children": 0, "pop_working": 1000,
            "pop_elderly": 0, "citycount": 1, "land": 1, "happiness": 99, "pollution": 0}
    population2.simulate_nation([prov], {}, 1.0, False, True, now=AFTER_DAWN,
                                happiness_bonus=3.0, home_mult=1.25)
    assert seen["homes"] == 125 and seen["happiness"] == 100.0  # capped at 100


def test_registry_isolates_a_failing_trait(monkeypatch):
    def boom(db, uid, *a, **k):
        raise RuntimeError("nope")

    monkeypatch.setitem(registry.HANDLERS, "golden_throne",
                        dict(registry.HANDLERS["golden_throne"], daily_tick=boom))
    cur = FakeCursor([("SELECT user_id, trait_key FROM nation_traits WHERE enabled", [(1, "golden_throne")])])
    assert registry.run_daily(cur) == {}  # no exception escapes the tick
    assert "ROLLBACK TO SAVEPOINT trait_daily" in cur.sql_log()


# ---------------------------------------------------------------- wiring + migration safety
def test_migration_is_additive_and_rerunnable():
    text = next((ROOT / "migrations").glob("*nation_traits_golden_throne.sql")).read_text()
    assert not re.search(r"\b(DROP|DELETE|TRUNCATE|UPDATE)\b", text, re.I)
    assert len(re.findall(r"CREATE TABLE IF NOT EXISTS", text)) == 5
    assert "CREATE TABLE " not in text.replace("CREATE TABLE IF NOT EXISTS", "")


def test_everything_is_wired():
    assert "traits_bp" in (ROOT / "app.py").read_text()
    assert "task_nation_traits" in (ROOT / "tasks.py").read_text()
    assert "nation_traits" in (ROOT / "app_core/celery_schedule.py").read_text()
    assert "traits" in (ROOT / "templates/country_v2.html").read_text()
    assert "trait-golden-throne.css" in (ROOT / "scripts/bundle_game_css.py").read_text()
    css = (ROOT / "static/css/trait-golden-throne.css").read_text()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # ignore comments
    assert not re.search(r"animation|transition|@keyframes", css)  # static by design


# ---------------------------------------------------------------- the Wall + population-only offering
def test_wall_lists_whose_people_were_given():
    from datetime import date as d
    cur = FakeCursor([
        ("FROM throne_days", [(d(2026, 11, 3), 9, 1, 1, "Pilgrim Surge", False)]),
        ("FROM throne_pilgrimages p JOIN users u", [(d(2026, 11, 3), 16, "Tester of the Game", 1000)]),
    ])
    rows, nxt = gt.wall_page(cur)
    assert nxt is None and rows[0]["souls_own"] == 9
    assert rows[0]["nations"] == [{"id": 16, "name": "Tester of the Game", "people": 1000}]


def test_only_population_can_be_offered():
    assert not hasattr(C, "PILGRIM_COST_MONEY")
    assert "money" not in (ROOT / "templates/partials/traits/golden_throne.html").read_text().lower()
    assert "money" not in (ROOT / "app_core/traits/routes.py").read_text().lower()
    assert "people" in (ROOT / "migrations").glob("*nation_traits_golden_throne.sql").__next__().read_text()
