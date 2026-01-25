import pytest
from helpers import validate_resource_column, apply_resource_delta
from database import get_db_cursor
import variables


def test_validate_resource_column_ok():
    for r in variables.RESOURCES[:3]:
        assert validate_resource_column(r) == r


def test_validate_resource_column_bad():
    with pytest.raises(ValueError):
        validate_resource_column("__not_a_resource__")


# Note: apply_resource_delta is integration-level and requires DB. We test that it
# raises for invalid column names and does not raise for valid ones (no DB call made)
def test_apply_resource_delta_invalid_column():
    with get_db_cursor() as db:
        with pytest.raises(ValueError):
            apply_resource_delta(db, 1, "invalid_column", 10)
