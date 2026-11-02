"""Province form failures come back as a toast on the same page; everything else keeps the real error response."""
import pytest

pytestmark = pytest.mark.no_server


def _call(headers):
    import app as application_module
    import province

    app = application_module.app
    with app.test_request_context("/buy/farms/252", method="POST", headers=headers, base_url="http://example.test"):
        from flask import get_flashed_messages

        resp = province._province_error(400, "You don't have enough money.")
        return resp, get_flashed_messages(with_categories=True)


def test_browser_form_post_from_province_page_redirects_with_toast():
    resp, flashed = _call({"Referer": "http://example.test/province/252", "Accept": "text/html,application/xhtml+xml"})
    assert resp.status_code == 302 and resp.location.startswith("/province/252?_=")
    assert flashed == [("error", "You don't have enough money.")]


@pytest.mark.parametrize(
    "headers",
    [
        {},  # API client / test client
        {"Referer": "http://example.test/province/252"},  # no Accept: html
        {"Referer": "http://evil.test/province/252", "Accept": "text/html"},  # other host
        {"Referer": "http://example.test/market", "Accept": "text/html"},  # not a province page
    ],
)
def test_everything_else_keeps_status_code_and_error_page(headers):
    resp, flashed = _call(headers)
    body, status = resp
    assert status == 400 and flashed == []
