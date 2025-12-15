from policies import get_policy_in_format, get_policies_from_request


def test_get_policy_in_format_present():
    policies = {"soldiers": [1, 3, 5]}
    out = get_policy_in_format(policies, "soldiers", 5)
    assert out["soldiers1"] is True
    assert out["soldiers2"] is False
    assert out["soldiers3"] is True


def test_get_policies_from_request():
    class DummyForm(dict):
        def get(self, k):
            return super().get(k)

    form = DummyForm({"soldiers1": "1", "soldiers3": "3"})
    out = get_policies_from_request("soldiers", 5, form)
    assert out == [1, 3]
