"""Regression: country page must not 500 when policy arrays are NULL."""

from policies import get_policy_in_format


def test_get_policy_in_format_handles_none_lists():
    policies = {"soldiers": None, "education": None}
    soldiers = get_policy_in_format(policies, "soldiers", 7)
    education = get_policy_in_format(policies, "education", 6)
    assert soldiers["soldiers1"] is False
    assert education["education1"] is False
