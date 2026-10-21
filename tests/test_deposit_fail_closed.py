import inspect

import pytest

pytestmark = pytest.mark.no_server


def test_deposit_never_defaults_to_donation():
    """A deposit with no explicit destination must be rejected, not donated."""
    import app_core.coalitions.routes as col_routes

    src = inspect.getsource(col_routes.deposit_into_bank)
    assert 'or "alliance"' not in src
    assert 'dest not in ("alliance", "personal")' in src


def test_personal_deposit_is_first_submit_button():
    """Enter-key submits the first button: it must be the reversible one."""
    for name in ("coalition.html", "coalition_v2.html"):
        html = open(f"templates/{name}", encoding="utf-8").read()
        assert html.index('value="personal"') < html.index('value="alliance"'), name
