"""Province API helpers: owner id resolution for JSON routes."""

import pytest

pytestmark = pytest.mark.no_server


def test_province_row_owner_id_realdict_keys():
    from province import _province_row_owner_id, _province_owned_by

    assert _province_row_owner_id({"owner_id": 42}) == 42
    assert _province_row_owner_id({"userid": 99}) == 99
    assert _province_row_owner_id({"userId": 7}) == 7
    assert _province_owned_by({"userid": 16}, 16) is True
    assert _province_owned_by({"userid": 16}, 17) is False
    assert _province_row_owner_id(None) is None


def test_wants_json_response_api_path():
    from helpers import _wants_json_response

    class Req:
        path = "/api/province/1/quick_build"
        headers = {}

    import helpers

    old = helpers.request
    helpers.request = Req()
    try:
        assert _wants_json_response() is True
    finally:
        helpers.request = old
