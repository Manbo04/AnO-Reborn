"""Regression: country page must not 500 when policy arrays are NULL."""

import pytest

from app_core.policies.repositories import format_policy_flags

pytestmark = pytest.mark.no_server


def test_get_policy_in_format_handles_none_lists():
    policies = {"soldiers": None, "education": None}
    soldiers = format_policy_flags(policies, "soldiers", 7)
    education = format_policy_flags(policies, "education", 6)
    assert soldiers["soldiers1"] is False
    assert education["education1"] is False
