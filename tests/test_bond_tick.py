"""Coverage for app_core/game_ticks/bond_tick.py's pure helpers -- the
actual DB-touching run_bond_tick() orchestration mirrors the same
task_runs/advisory-lock pattern shared by every other game_ticks module and
isn't re-tested here (see tests/test_loan_interest.py for the precedent).
"""
import pytest

from app_core.game_ticks import bond_tick

pytestmark = pytest.mark.no_server


# ---------------------------------------------------------------------------
# compute_daily_bond_charge
# ---------------------------------------------------------------------------

def test_full_interest_paid_no_escrow():
    interest, escrow, missed = bond_tick.compute_daily_bond_charge(
        principal=1000, daily_interest_rate=0.01, auto_escrow=False, term_days=10, available_gold=100
    )
    assert interest == 10
    assert escrow == 0
    assert missed is False


def test_interest_shortfall_is_flagged_as_missed():
    interest, escrow, missed = bond_tick.compute_daily_bond_charge(
        principal=1000, daily_interest_rate=0.01, auto_escrow=False, term_days=10, available_gold=4
    )
    assert interest == 4
    assert escrow == 0
    assert missed is True


def test_auto_escrow_paid_after_interest_when_gold_allows():
    interest, escrow, missed = bond_tick.compute_daily_bond_charge(
        principal=1000, daily_interest_rate=0.01, auto_escrow=True, term_days=10, available_gold=1000
    )
    assert interest == 10  # 1% of 1000
    assert escrow == 100  # 1000 / 10 days
    assert missed is False


def test_interest_prioritized_over_escrow_when_gold_is_tight():
    # Only enough gold to cover interest, nothing left for the escrow leg.
    interest, escrow, missed = bond_tick.compute_daily_bond_charge(
        principal=1000, daily_interest_rate=0.01, auto_escrow=True, term_days=10, available_gold=10
    )
    assert interest == 10
    assert escrow == 0
    assert missed is False


def test_zero_gold_misses_everything():
    interest, escrow, missed = bond_tick.compute_daily_bond_charge(
        principal=1000, daily_interest_rate=0.01, auto_escrow=True, term_days=10, available_gold=0
    )
    assert interest == 0
    assert escrow == 0
    assert missed is True


# ---------------------------------------------------------------------------
# compute_maturity_settlement
# ---------------------------------------------------------------------------

def test_maturity_fully_covered_by_gold():
    garnished, shortfall = bond_tick.compute_maturity_settlement(
        principal=1000, escrowed_principal=0, available_gold=1000
    )
    assert garnished == 1000
    assert shortfall == 0


def test_maturity_partially_prepaid_via_escrow():
    garnished, shortfall = bond_tick.compute_maturity_settlement(
        principal=1000, escrowed_principal=600, available_gold=1000
    )
    assert garnished == 400  # only the un-escrowed remainder is due now
    assert shortfall == 0


def test_maturity_shortfall_when_issuer_cant_cover_remainder():
    garnished, shortfall = bond_tick.compute_maturity_settlement(
        principal=1000, escrowed_principal=0, available_gold=300
    )
    assert garnished == 300
    assert shortfall == 700  # this is what becomes garnishment_owed -- not forgiven


def test_maturity_fully_escrowed_needs_no_gold():
    garnished, shortfall = bond_tick.compute_maturity_settlement(
        principal=1000, escrowed_principal=1000, available_gold=0
    )
    assert garnished == 0
    assert shortfall == 0
