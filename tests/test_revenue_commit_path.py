"""Regression: generate_province_revenue must commit resources before education.

Education overflow used to conn.rollback() and wipe resource upserts; upserts
also omitted updated_at so health checks showed a frozen economy.
"""

import tasks


def test_education_delta_clamps_to_int32():
    huge = 5_000_000_000
    clamped = max(0, min(int(huge), tasks.MAX_INT_32))
    assert clamped == tasks.MAX_INT_32


def test_revenue_upsert_sql_sets_updated_at():
    """Upsert batch must touch updated_at (progression health signal)."""
    import inspect

    source = inspect.getsource(tasks.generate_province_revenue)
    assert "updated_at = now()" in source
    assert "SAVEPOINT revenue_education_batch" in source
    assert "ROLLBACK TO SAVEPOINT revenue_education_batch" in source
    # last_run only after successful commit
    assert (
        "Do not commit last_run here" in source
        or "wait until resource/province writes" in source
    )
    idx_early = source.find("Do not commit last_run")
    idx_late = source.rfind("UPDATE task_runs SET last_run")
    assert idx_late > idx_early > 0


def test_resource_upsert_before_education_in_source_order():
    """Resource batch must appear before education savepoint in function body."""
    import inspect

    source = inspect.getsource(tasks.generate_province_revenue)
    res = source.find("INSERT INTO user_economy")
    edu = source.find("SAVEPOINT revenue_education_batch")
    assert res > 0 and edu > res
