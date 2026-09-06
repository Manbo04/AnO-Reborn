"""Coverage for app_core/game_ticks/loan_interest.py's pure helper -- the
actual DB-touching run_loan_interest() orchestration mirrors the same
task_runs/advisory-lock pattern shared by every other game_ticks module
and isn't re-tested here (see tests/test_disasters.py for the precedent).
"""
import pytest

from app_core.game_ticks import loan_interest

pytestmark = pytest.mark.no_server


def test_full_interest_paid_from_gold():
    garnished, new_balance = loan_interest.compute_interest_charge(
        balance=1000, interest_rate=0.01, available_gold=100
    )
    assert garnished == 10  # 1% of 1000, well within the 100 gold available
    assert new_balance == 1000  # paid in full, balance unchanged


def test_shortfall_compounds_into_balance():
    garnished, new_balance = loan_interest.compute_interest_charge(
        balance=1000, interest_rate=0.01, available_gold=4
    )
    assert garnished == 4  # only what was available
    assert new_balance == 1006  # 10 due - 4 paid = 6 shortfall added to balance


def test_zero_gold_all_of_interest_compounds():
    garnished, new_balance = loan_interest.compute_interest_charge(
        balance=1000, interest_rate=0.01, available_gold=0
    )
    assert garnished == 0
    assert new_balance == 1010


def test_zero_balance_no_charge():
    garnished, new_balance = loan_interest.compute_interest_charge(
        balance=0, interest_rate=0.01, available_gold=500
    )
    assert garnished == 0
    assert new_balance == 0
