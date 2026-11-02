"""Thank-you gift: window gating, once-per-player claim, ledger credit (DB-free)."""
from datetime import date

import pytest

from app_core import halloween
from tests._fake_db import FakeCursor

pytestmark = pytest.mark.no_server

DAY1 = date(2026, 11, 2)  # first day of the window


def test_only_inside_the_window():
    assert halloween.is_halloween(DAY1)
    assert halloween.is_halloween(date(2026, 11, 16))  # last day inclusive
    assert not halloween.is_halloween(date(2026, 11, 1))
    assert not halloween.is_halloween(date(2026, 11, 17))
    assert not halloween.is_halloween(date(2027, 10, 31))


def test_env_override(monkeypatch):
    monkeypatch.setenv("HALLOWEEN_GIFT_DATE", "2025-11-05")
    assert halloween.gift_date() == date(2025, 11, 5)
    monkeypatch.setenv("HALLOWEEN_GIFT_DATE", "garbage")
    assert halloween.gift_date() != date(2025, 11, 5)


def test_wrong_day_touches_nothing():
    cur = FakeCursor()
    ok, _, amt = halloween.claim_gift(cur, 1, today=date(2026, 6, 1))
    assert not ok and amt == 0 and cur.executed == []


def test_first_claim_credits_once_second_is_refused():
    cur = FakeCursor([("INSERT INTO halloween_gift_claims", [(1,)])])
    cur.rowcount = 1
    ok, _, amt = halloween.claim_gift(cur, 7, today=DAY1)
    assert ok and amt == halloween.HALLOWEEN_GIFT_AMOUNT
    sql = cur.sql_log()
    assert any("UPDATE stats SET gold=gold+" in s for s in sql)
    assert cur.executed[0][1] == (7, 2026, halloween.HALLOWEEN_GIFT_AMOUNT)

    dup = FakeCursor([("INSERT INTO halloween_gift_claims", [])])  # conflict -> no row
    ok, _, amt = halloween.claim_gift(dup, 7, today=DAY1)
    assert not ok and amt == 0
    assert not any("UPDATE stats" in s for s in dup.sql_log())


def test_missing_stats_row_rolls_back():
    cur = FakeCursor([("INSERT INTO halloween_gift_claims", [(1,)])])
    cur.rowcount = 0
    with pytest.raises(RuntimeError):
        halloween.claim_gift(cur, 7, today=DAY1)


def test_modal_template_compiles():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("templates"))
    env.get_template("_halloween_gift.html")
    env.get_template("layout.html")
