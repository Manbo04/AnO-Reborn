"""Province status partial uses responsive card grid markup."""
import pytest

pytestmark = pytest.mark.no_server


def _render_province_status(**overrides):
    import app as application_module

    defaults = {
        "has_power": True,
        "enough_rations": False,
        "enough_consumer_goods": True,
        "distribution_capacity": 17_000_000,
        "cg_distribution_capacity": 12_000_000,
        "nation_distribution": {
            "uncovered_population": 7_200_000,
            "stockpile_bottleneck": True,
        },
    }
    defaults.update(overrides)
    with application_module.app.app_context():
        return application_module.app.jinja_env.get_template(
            "partials/province_status.html"
        ).render(**defaults)


def test_province_status_renders_card_grid():
    html = _render_province_status()
    assert "province-status-grid" in html
    assert "province-status-card" in html
    assert "province-status-card--ok" in html
    assert "province-status-card--bad" in html
    assert "notificationparent" not in html
    assert "notificationchild" not in html


def test_province_status_merges_ration_warnings_in_one_card():
    html = _render_province_status()
    cards = html.split('<div class="province-status-card')[1:]
    ration_card = next(c for c in cards if "rations" in c.lower())
    assert "province-status-card__detail" in ration_card
    assert "province-status-card__detail--warn" in ration_card
    assert "distribution serves" in ration_card
    assert "distribution buildings cannot reach" in ration_card
