"""Hidden-from-rankings + untargetable nations.

DB-free: rules are exercised against a scripted cursor.
"""
import re
from pathlib import Path

import pytest

from app_core import visibility
from app_core.visibility import UNTARGETABLE_MSG
from tests._fake_db import FakeCursor

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parent.parent


def _cur(untargetable):
    return FakeCursor([("untargetable", [(untargetable,)])])


def test_is_untargetable_reads_flag():
    assert visibility.is_untargetable(_cur(True), 1) is True
    assert visibility.is_untargetable(_cur(False), 2) is False


def test_missing_column_means_targetable():
    # No rule matches -> fetchone() None, exactly what a failed read yields.
    assert visibility.is_untargetable(FakeCursor(), 1) is False


def test_garbage_ids_are_not_untargetable():
    assert visibility.is_untargetable(_cur(True), "abc") is False
    assert visibility.is_untargetable(_cur(True), None) is False


def test_self_is_exempt_and_others_blocked():
    assert visibility.blocks_interaction(_cur(True), 1, 1) is False
    assert visibility.blocks_interaction(_cur(True), 5, 1) is True
    assert visibility.blocks_interaction(_cur(False), 5, 2) is False


def test_ranked_sql_excludes_bots_and_hidden():
    sql = visibility.ranked_sql("x")
    assert "x.auth_type IS DISTINCT FROM 'bot'" in sql
    assert "x.hidden_from_rankings" in sql


def test_place_bounty_on_untargetable_nation_is_refused(monkeypatch):
    from app_core.bounties import services

    monkeypatch.setattr(services, "user_exists", lambda db, uid: True)
    cur = _cur(True)
    ok, msg, category = services.place_bounty(cur, 5, 1, 10**9)
    assert (ok, msg, category) == (False, UNTARGETABLE_MSG, "danger")
    assert not any(s.startswith(("UPDATE", "INSERT")) for s in cur.sql_log())


def test_offer_treaty_to_untargetable_nation_is_refused(monkeypatch):
    from app_core.treaties import services

    monkeypatch.setattr(services, "find_user_id_by_username", lambda db, n: 1)
    monkeypatch.setattr(
        services,
        "insert_treaty_offer",
        lambda *a, **k: pytest.fail("offer must not be inserted"),
    )
    ok, msg, _ = services.offer_treaty(_cur(True), 5, "Dede", "alliance")
    assert not ok and msg == UNTARGETABLE_MSG


def test_trade_agreement_with_untargetable_nation_is_refused(monkeypatch):
    from app_core.trade_agreements import services

    monkeypatch.setattr(services, "resolve_trade_partner_id", lambda *a: 1)
    monkeypatch.setattr(
        services,
        "insert_agreement",
        lambda *a, **k: pytest.fail("agreement must not be inserted"),
    )
    ok, msg = services.create_agreement(
        _cur(True), 5, "1", "", "food", "10", "gold", "10", "24", None, ""
    )
    assert not ok and msg == UNTARGETABLE_MSG


def test_spy_operation_on_untargetable_nation_is_refused():
    from app_core.intelligence import services

    cur = _cur(True)
    ok, status, msg, entry = services.resolve_spy_operation(cur, 5, 1, 3, "intel")
    assert (ok, status, msg, entry) == (False, 403, UNTARGETABLE_MSG, None)
    assert not any(s.startswith(("UPDATE", "INSERT")) for s in cur.sql_log())


def _src(rel):
    return (ROOT / rel).read_text()


@pytest.mark.parametrize(
    "rel",
    [
        "wars/routes.py",
        "app_core/coalitions/routes.py",
        "app_core/market/routes.py",
        "app_core/chat/routes.py",
        "app_core/game_map/routes.py",
    ],
)
def test_route_level_guards_are_wired(rel):
    assert "is_untargetable" in _src(rel) or "blocks_interaction" in _src(rel)


def test_every_ranking_query_filters_hidden_nations():
    stats = _src("statistics.py")
    # all four ranked queries + the alliance influence sub-select
    assert stats.count("hidden_from_rankings") >= 5
    assert "hidden_from_rankings" in _src("discord_bot/panels/data.py")
    assert "hidden_from_rankings" in _src("bot_api.py")
    assert "untargetable" in _src("repositories/country_repository.py")


def test_migration_adds_both_columns_and_flags_owner():
    mig = next((ROOT / "migrations").glob("*_hidden_untargetable_flags.sql"))
    text = mig.read_text()
    assert re.search(r"ADD COLUMN IF NOT EXISTS hidden_from_rankings", text)
    assert re.search(r"ADD COLUMN IF NOT EXISTS untargetable", text)
    assert "untargetable = TRUE WHERE id = 1" in text


def test_war_target_finder_skips_untargetable_nations():
    src = _src("wars/routes.py")
    assert "AND NOT COALESCE(u.untargetable, FALSE)" in src
