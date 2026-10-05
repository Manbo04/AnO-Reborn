from flask import Flask

from helpers import redirect_back

app = Flask(__name__)


def _location(referrer=None, form=None, path="/buy_offer/1"):
    headers = {"Referer": referrer} if referrer else {}
    with app.test_request_context(
        path, method="POST", headers=headers, data=form or {}, base_url="https://affairsandorder.org"
    ):
        return redirect_back("/market").headers["Location"]


def test_returns_to_same_page_with_filters():
    assert _location("https://affairsandorder.org/market?resource=rations&per_side=50") == (
        "/market?resource=rations&per_side=50"
    )


def test_relative_next_field_wins():
    assert _location("https://affairsandorder.org/market", {"next": "/my_offers"}) == "/my_offers"


def test_external_and_protocol_relative_targets_fall_back():
    assert _location("https://evil.example/market") == "/market"
    assert _location(None, {"next": "//evil.example/x"}) == "/market"
    assert _location(None, {"next": "/\\evil.example"}) == "/market"


def test_no_referrer_or_self_falls_back():
    assert _location(None) == "/market"
    assert _location("https://affairsandorder.org/buy_offer/1") == "/market"
