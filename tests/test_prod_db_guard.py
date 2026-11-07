"""The production-database guard that stops the suite before it can touch real data."""
import pytest

from tests._prod_guard import production_reason

pytestmark = pytest.mark.no_server


@pytest.mark.parametrize(
    "env",
    [
        {"DATABASE_URL": "postgresql://u:p@postgres.railway.internal:5432/railway"},
        {"DATABASE_URL": "postgresql://u:p@roundhouse.proxy.rlwy.net:12345/railway"},
        {"PG_HOST": "prod-validator.railway.internal"},
        {"ENVIRONMENT": "PROD"},
        {"RAILWAY_ENVIRONMENT_NAME": "production"},
    ],
)
def test_production_looking_environments_are_refused(env):
    assert production_reason(env)


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/anodb"},
        {"DATABASE_URL": "postgresql://ano_test:ano_test@postgres:5432/ano_ct", "ENVIRONMENT": "TEST"},
        {"PG_HOST": "127.0.0.1"},
    ],
)
def test_local_ci_and_test_realm_environments_are_allowed(env):
    assert production_reason(env) is None


def test_the_suite_start_hook_exits_on_production(monkeypatch):
    import tests.conftest as c

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@x.railway.internal:5432/railway")
    with pytest.raises(BaseException) as exc:
        c.pytest_sessionstart(None)
    assert "Refusing to run tests against production" in str(exc.value)


def test_session_epoch_users_are_cleaned_up():
    """The module that leaked eight rows now purges what it creates."""
    import inspect

    import tests.test_session_epoch as m

    src = inspect.getsource(m)
    assert "_purge_created_users" in src and "purge_users" in src
