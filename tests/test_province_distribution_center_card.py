"""Distribution Centers must have a buy card on the province page.

The Retail group lists distribution_centers, but the card used to be wrapped
in `units["distribution_centers"] > 0`, so players with none saw an empty gap.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["province.html"])
def test_distribution_center_card_not_gated_on_owned_count(name):
    src = (ROOT / "templates" / name).read_text(encoding="utf-8")
    assert 'units["distribution_centers"] > 0' not in src
    assert "(Deprecated)" not in src
    assert "/buy/distribution_centers/" in src
    assert "/sell/distribution_centers/" in src


def test_v2_distribution_center_card_comes_from_catalog_and_is_always_rendered():
    cat = (ROOT / "templates" / "partials" / "province_catalog.html").read_text(encoding="utf-8")
    assert '"unit": "distribution_centers"' in cat
    macro = (ROOT / "templates" / "macros" / "province_ui.html").read_text(encoding="utf-8")
    assert "'/buy/' ~ unit" in macro and "'/sell/' ~ unit" in macro
    assert 'units["distribution_centers"] > 0' not in macro + cat
