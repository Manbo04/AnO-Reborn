"""Aggregated activity counters: correctness, privacy, flag gating, contention and cost."""
import datetime as dt
import os
import threading
import time

import pytest

from app_core import activity
from balance import activity as balance_activity
from balance import snapshot
from balance.metrics import Nation, retention

pytestmark = pytest.mark.no_server

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261108_0900_activity_counters.sql")


# ---------------------------------------------------------------- sketch
def _estimate(ids, day="2026-11-08"):
    reg = activity.new_sketch()
    for i in ids:
        activity.sketch_add(reg, activity._hash64(day, i))
    return activity.sketch_estimate(reg)


def test_sketch_counts_distinct_users_within_ten_percent():
    for n in (5, 120, 1000, 5000):
        est = _estimate(range(1, n + 1))
        assert abs(est - n) <= max(2, 0.1 * n), (n, est)


def test_sketch_ignores_repeats_and_merges_as_a_union():
    ids = list(range(1, 301))
    assert abs(_estimate(ids * 5) - _estimate(ids)) < 1
    a, b = activity.new_sketch(), activity.new_sketch()
    for i in range(1, 201):
        activity.sketch_add(a, activity._hash64("d", i))
    for i in range(101, 301):
        activity.sketch_add(b, activity._hash64("d", i))
    merged = activity.sketch_merge(a, bytes(b))
    assert abs(activity.sketch_estimate(merged) - 300) <= 30


def test_sketch_is_fixed_size_and_holds_no_ids():
    reg = activity.new_sketch()
    for i in range(1, 5000):
        activity.sketch_add(reg, activity._hash64("d", i))
    assert len(reg) == 1024 and max(reg) <= 54  # registers, never ids


# ---------------------------------------------------------------- mapping
def test_action_for_only_counts_successful_posts_on_known_rules():
    assert activity.action_for("POST", "/build_structure", 302) == "build"
    assert activity.action_for("POST", "/declare_war", 200) == "declare_war"
    assert activity.action_for("GET", "/build_structure", 200) is None
    assert activity.action_for("POST", "/build_structure", 400) is None
    assert activity.action_for("POST", "/not_a_game_route", 200) is None
    assert activity.action_for("POST", None, 200) is None


def test_every_mapped_rule_is_a_real_post_route():
    from app import app

    posts = {r.rule for r in app.url_map.iter_rules() if "POST" in r.methods}
    missing = sorted(set(activity.ACTION_RULES) - posts)
    assert not missing, f"mapped rules that no longer exist: {missing}"


# ---------------------------------------------------------------- cohorts
def test_cohorts_split_new_top_decile_and_rest():
    now = dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc)
    recent = now - dt.timedelta(days=1)
    rows = [(1, "2026-11-07", 5, recent)]  # new
    rows += [(100 + i, "2026-06-01", 1000 + i, recent) for i in range(20)]  # 20 active older nations
    rows += [(900, "2026-06-01", 10**12, now - dt.timedelta(days=60))]  # rich but long gone
    rows += [(901, "bad-date", 5, recent)]
    out = activity.refresh_cohorts(rows, now)
    assert out[1] == "new"
    assert sorted(u for u, c in out.items() if c == "top10") == [118, 119]
    assert out[900] == "other" and out[901] == "other"


# ---------------------------------------------------------------- flag gating
def _app():
    from flask import Flask, session

    app = Flask("t")
    app.secret_key = "x"

    @app.route("/build_structure", methods=["POST"])
    def build():
        session["user_id"] = 7
        return "ok"

    @app.route("/other", methods=["POST"])
    def other():
        session["user_id"] = 7
        return "ok"

    @app.route("/fail", methods=["POST"])
    def fail():
        return "no", 400

    app.url_map._rules_by_endpoint  # noqa: B018 (ensure map is built)
    activity.ACTION_RULES.setdefault("/fail", "build")
    activity.init_activity(app)
    return app


@pytest.fixture(autouse=True)
def _clean_buffer():
    with activity._lock:
        activity._counts.clear()
        activity._sketches.clear()
    activity._cohorts = {7: "top10"}
    activity._cohorts_at = time.monotonic()
    yield
    activity.ACTION_RULES.pop("/fail", None)


def test_hook_records_nothing_when_the_flag_is_off(monkeypatch):
    from app_core import feature_flags

    monkeypatch.setattr(feature_flags, "is_on", lambda *a, **k: False)
    c = _app().test_client()
    with c.session_transaction() as s:
        s["user_id"] = 7
    c.post("/build_structure")
    assert not activity._counts and not activity._sketches


def test_hook_counts_successes_only_when_the_flag_is_on(monkeypatch):
    from app_core import feature_flags

    monkeypatch.setattr(feature_flags, "is_on", lambda *a, **k: True)
    monkeypatch.setattr(activity, "flush", lambda *a, **k: False)
    c = _app().test_client()
    with c.session_transaction() as s:
        s["user_id"] = 7
    c.post("/build_structure")
    c.post("/build_structure")
    c.post("/other")  # unmapped
    c.post("/fail")  # mapped but 400
    keys = {(a, co): n for (_d, a, co), n in activity._counts.items()}
    assert keys == {("build", "top10"): 2}


def test_hook_never_breaks_the_response(monkeypatch):
    from app_core import feature_flags

    def boom(*a, **k):
        raise RuntimeError("flags down")

    monkeypatch.setattr(feature_flags, "is_on", boom)
    c = _app().test_client()
    with c.session_transaction() as s:
        s["user_id"] = 7
    assert c.post("/build_structure").status_code == 200


# ---------------------------------------------------------------- database
@pytest.fixture
def tables():
    from database import get_db_connection

    sql = open(MIGRATION).read()
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(sql)
        db.execute("DELETE FROM activity_daily WHERE day >= '2099-01-01'")
        db.execute("DELETE FROM activity_daily_users WHERE day >= '2099-01-01'")
        conn.commit()
    yield
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM activity_daily WHERE day >= '2099-01-01'")
        db.execute("DELETE FROM activity_daily_users WHERE day >= '2099-01-01'")
        conn.commit()


def _sum(day="2099-01-01"):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT COALESCE(SUM(count), 0) FROM activity_daily WHERE day = %s", (day,))
        return int(db.fetchone()[0])


def test_flush_adds_counts_and_merges_sketches(tables):
    from database import get_db_connection

    for uid in range(1, 51):
        activity.record("build", uid, day="2099-01-01", cohort="other")
    assert activity.flush(force=True) is True
    for uid in range(26, 76):
        activity.record("build", uid, day="2099-01-01", cohort="other")
    assert activity.flush(force=True) is True
    assert _sum() == 100
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT hll FROM activity_daily_users WHERE day = '2099-01-01' AND cohort = 'other'")
        est = activity.sketch_estimate(bytes(db.fetchone()[0]))
    assert abs(est - 75) <= 8  # 75 distinct users, 100 actions


def test_tables_hold_no_user_ids(tables):
    from database import get_db_connection

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name IN ('activity_daily', 'activity_daily_users')"
        )
        cols = {r[0] for r in db.fetchall()}
    assert cols == {"day", "action", "cohort", "count", "hll"}


def test_concurrent_writers_lose_nothing_and_do_not_deadlock(tables):
    """Two web processes flushing the same day at once: totals stay exact, no deadlock."""
    errors = []

    def writer(seed):
        try:
            for _ in range(10):
                counts = {("2099-01-01", a, c): 3 for a in ("build", "attack", "trade") for c in ("new", "other")}
                reg = activity.new_sketch()
                for u in range(seed * 100, seed * 100 + 20):
                    activity.sketch_add(reg, activity._hash64("2099-01-01", u))
                activity._write(counts, {("2099-01-01", "other"): bytes(reg), ("2099-01-01", "new"): bytes(reg)})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    elapsed = time.perf_counter() - start
    assert not errors, errors
    assert _sum() == 6 * 10 * 6 * 3
    assert elapsed < 30


def test_a_failed_flush_keeps_counts_for_the_next_try(tables, monkeypatch):
    activity.record("build", 1, day="2099-01-01", cohort="other")

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(activity, "_write", boom)
    assert activity.flush(force=True) is False
    assert activity._counts[("2099-01-01", "build", "other")] == 1
    monkeypatch.undo()
    assert activity.flush(force=True) is True
    assert _sum() == 1


# ---------------------------------------------------------------- cost
def test_recording_is_cheap_on_the_hot_path():
    start = time.perf_counter()
    for i in range(20000):
        activity.record("build", i % 300, day="2099-01-01", cohort="other")
    per_call_us = (time.perf_counter() - start) / 20000 * 1e6
    assert per_call_us < 200, f"{per_call_us:.0f} microseconds per recorded action"


def test_buffer_is_bounded():
    for i in range(activity.MAX_BUFFER_KEYS + 500):
        activity.record(f"a{i}", 1, day="2099-01-01", cohort="other")
    assert len(activity._counts) <= activity.MAX_BUFFER_KEYS


# ---------------------------------------------------------------- harness
def _nation(i, age, idle, ai=False):
    return Nation(idx=i, gold=1, net_per_hour=1.0, age_days=age, idle_days=idle, is_ai=ai)


def test_retention_uses_last_seen_and_reports_the_gaps():
    ns = [
        _nation(0, 40, 0),      # old, still active: retained D1/D7/D30
        _nation(1, 40, 39.5),   # last seen about half a day after signup: not D1
        _nation(2, 40, 30),     # last seen 10 days after signup: D1, D7, not D30
        _nation(3, 5, 0),       # too young for D7 and D30, retained D1
        _nation(4, 40, 9999),   # no activity record
        _nation(5, 40, 0, ai=True),
        _nation(6, 9999, 0),    # bad signup date: excluded
    ]
    r = retention(ns)
    assert r["d1"] == {"matured": 5, "retained": 3, "rate": 0.6, "no_activity_record": 1}
    assert r["d7"]["matured"] == 4 and r["d7"]["retained"] == 2
    assert r["d30"]["matured"] == 4 and r["d30"]["retained"] == 1
    assert "not exact day-N" in r["basis"]


def test_breakdown_reports_shares_per_cohort_and_distinct_users():
    reg = activity.new_sketch()
    for u in range(1, 61):
        activity.sketch_add(reg, activity._hash64("2026-11-07", u))
    counts = [
        (dt.date(2026, 11, 7), "attack", "top10", 30),
        (dt.date(2026, 11, 7), "build", "top10", 10),
        (dt.date(2026, 11, 7), "build", "new", 50),
    ]
    out = balance_activity.breakdown(counts, [(dt.date(2026, 11, 7), "top10", bytes(reg))])
    top = out["cohorts"]["top10"]
    assert top["total"] == 40 and top["actions"][0]["action"] == "attack" and top["actions"][0]["share"] == 0.75
    assert abs(out["distinct_active_by_day"][0]["total"] - 60) <= 6
    assert out["collecting"] is False
    assert balance_activity.breakdown([], [])["collecting"] is True


def test_fetch_reports_missing_tables_instead_of_failing():
    class Cur:
        def execute(self, sql):
            self.sql = sql

        def fetchone(self):
            return (False,)

    out = balance_activity.fetch(Cur())
    assert out["collecting"] is True and "not created" in out["error"]


def test_activity_queries_are_single_selects():
    snapshot.assert_select_only(balance_activity.COUNTS_SQL)
    snapshot.assert_select_only(balance_activity.USERS_SQL)
