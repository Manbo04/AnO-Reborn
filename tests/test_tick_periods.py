"""Period gate for the hourly/daily economy ticks (common.claim_tick_period).

Replays the two failure modes of the old "skip if last run < 55 min" gate:
  * a delayed run followed by the next on-time run must BOTH happen
    (old gate skipped the second -> lost hour, the 2026-10-03 tax skip);
  * a late nudge/deploy run in an hour that already ran must NOT happen
    (old gate allowed it once 55 min passed -> upkeep billed up to 6x, 10-05).
"""
import datetime as dt

import pytest

from app_core.game_ticks.common import claim_tick_period, current_period, should_skip_task
from database import get_db_connection

pytestmark = pytest.mark.no_server
UTC = dt.timezone.utc


def at(h, m, day=6):
    return dt.datetime(2026, 10, day, h, m, tzinfo=UTC)


def test_current_period_units():
    assert current_period("tax_income", at(13, 25)) == at(13, 0)
    assert current_period("bond_tick", at(13, 25)) == dt.datetime(2026, 10, 6, tzinfo=UTC)
    assert current_period("global_tick", at(13, 25)) is None  # not period-gated


@pytest.fixture
def task():
    name = "tax_income"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("DELETE FROM task_runs WHERE task_name = %s", (name,))
        db.execute("INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL)", (name,))
        conn.commit()
    yield name
    with get_db_connection() as conn:
        conn.cursor().execute("DELETE FROM task_runs WHERE task_name = %s", (name,))
        conn.commit()


def _claim(name, when):
    with get_db_connection() as conn:
        return claim_tick_period(conn.cursor(), name, now=when)


def test_delayed_run_does_not_swallow_the_next_hour(task):
    assert _claim(task, at(12, 50))      # hour 12, 50 min late
    assert _claim(task, at(13, 25))      # hour 13 on time: must run (old gate: skipped)


def test_late_nudge_cannot_bill_an_hour_twice(task):
    assert _claim(task, at(13, 0))
    assert not _claim(task, at(13, 40))  # watchdog/deploy nudge, same hour
    assert not _claim(task, at(13, 59))
    assert _claim(task, at(14, 0))


def test_claim_is_committed_before_work(task):
    """A rollback of the tick's work transaction must not release the hour."""
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute("SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE", (task,))
        assert claim_tick_period(db, task, now=at(15, 0))
        db.execute("UPDATE task_runs SET last_run = now() WHERE task_name = %s", (task,))
        conn.rollback()  # the tick failed after claiming
    assert not _claim(task, at(15, 30))


def test_should_skip_task_uses_period_gate_when_given_db(task):
    with get_db_connection() as conn:
        db = conn.cursor()
        recent = (dt.datetime.now(UTC) - dt.timedelta(minutes=1),)
        # last_run 1 minute ago, but this hour not yet claimed -> runs
        assert should_skip_task(recent, task, db=db) is False
        # second attempt in the same hour -> skipped
        assert should_skip_task(recent, task, db=db) is True
