import pytest

pytestmark = pytest.mark.no_server


def test_unrecorded_workers_still_fill_jobs():
    from app_core.economy.workforce import jobs_available

    # Seeded starter province: 600k working, no education records yet.
    assert jobs_available(0, 600_000) == 600_000


def test_education_records_above_working_pop_are_kept():
    from app_core.economy.workforce import jobs_available

    assert jobs_available(900_000, 600_000) == 900_000


def test_none_and_zero_are_safe():
    from app_core.economy.workforce import jobs_available

    assert jobs_available(None, None) == 0
    assert jobs_available(0, 0) == 0


def test_efficiency_copies_all_use_the_shared_rule():
    import inspect

    from app_core.economy import province_energy
    from app_core.game_ticks import population, revenue
    import countries

    for mod in (province_energy, population, revenue, countries):
        assert "app_core.economy.workforce" in inspect.getsource(mod), mod.__name__
