"""Test personal bank accounts for coalition members."""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, session


@pytest.mark.no_server
def test_withdraw_personal_from_bank_route_registration():
    """Verify withdraw_personal_from_bank route is registered in coalition routes."""
    from app import app
    adapter = app.url_map.bind("localhost")
    match = adapter.match("/withdraw_personal_from_bank/123", method="POST")
    assert match[0] == "withdraw_personal_from_bank"


@pytest.mark.no_server
def test_personal_bank_template_elements():
    """Verify template contains personal balance column and withdraw button."""
    with open("templates/coalition_v2.html", "r", encoding="utf-8") as f:
        v2_content = f.read()
    assert "Personal Balance" in v2_content
    assert "/withdraw_personal_from_bank/" in v2_content
    assert "Withdraw Personal" in v2_content

    with open("templates/coalition.html", "r", encoding="utf-8") as f:
        v1_content = f.read()
    assert "Personal Balance" in v1_content
    assert "/withdraw_personal_from_bank/" in v1_content
    assert "Withdraw Personal" in v1_content


@pytest.mark.no_server
def test_contribution_queries_do_not_use_missing_stats_flag_column():
    """stats has no flag_data column (it lives on users); selecting s.flag_data
    made both contribution queries fail, so every personal balance showed 0."""
    with open("app_core/coalitions/routes.py", "r", encoding="utf-8") as f:
        src = f.read()
    assert "s.flag_data" not in src
    assert "u.flag_data, cbc.resource" in src


@pytest.mark.no_server
def test_adjust_personal_bank_route_registration():
    """Verify adjust_personal_bank route is registered in coalition routes."""
    from app import app
    adapter = app.url_map.bind("localhost")
    match = adapter.match("/adjust_personal_bank/123", method="POST")
    assert match[0] == "adjust_personal_bank"


@pytest.mark.no_server
def test_personal_bank_management_template_elements():
    """Verify templates contain Alliance Donation, Personal Deposit, and Management elements."""
    with open("templates/coalition_v2.html", "r", encoding="utf-8") as f:
        v2_content = f.read()
    assert "Donate to Alliance" in v2_content
    assert "Personal Deposit" in v2_content
    assert "Manage Member Personal Balances" in v2_content
    assert "/adjust_personal_bank/" in v2_content

    with open("templates/coalition.html", "r", encoding="utf-8") as f:
        v1_content = f.read()
    assert "Donate to Alliance" in v1_content
    assert "Personal Deposit" in v1_content
    assert "Manage Member Personal Balances" in v1_content
    assert "/adjust_personal_bank/" in v1_content


@pytest.mark.no_server
def test_deposit_destination_branches_in_routes():
    """Verify routes.py handles personal vs alliance donation destination."""
    with open("app_core/coalitions/routes.py", "r", encoding="utf-8") as f:
        src = f.read()
    assert 'request.form.get("deposit_destination")' in src
    assert 'is_personal = (dest == "personal")' in src
    assert 'log_kind = "personal" if is_personal else "donation"' in src


@pytest.mark.no_server
def test_adjust_personal_bank_implementation():
    """Verify adjust_personal_bank enforces permissions, updates col_bank_contributions, and logs."""
    with open("app_core/coalitions/routes.py", "r", encoding="utf-8") as f:
        src = f.read()
    assert "def adjust_personal_bank(coalition_id):" in src
    assert "roles=[\"leader\", \"deputy_leader\", \"banker\"]" in src
    assert "action_type == \"deduct\"" in src
    assert "action_type == \"set\"" in src
    assert "col_bank_contributions" in src
    assert "'adjustment'" in src
