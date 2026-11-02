"""Province page (province_v2.html) renders with tabs, one macro row per building, and every buy/sell action."""
import re

import pytest

from province_page_context import render

pytestmark = pytest.mark.no_server

BIOMES = ["Tundra", "Desert", "Boreal Forest", "Grassland", "Savanna", "Mountain Range", "Jungle"]


def _actions(html):
    return set(re.findall(r'formaction="(/(?:buy|sell)/[a-zA-Z_]+)/252"', html))


def _catalog():
    import app as application_module

    tpl = application_module.app.jinja_env.get_template("partials/province_catalog.html")
    return tpl.make_module({}).PROVINCE_CATALOG


@pytest.mark.parametrize("biome", BIOMES)
def test_catalog_terrain_matches_canonical_biome_table(biome):
    from app_core.economy.biome_buildings import BIOME_MINES

    shown = {e["unit"] for e in _catalog() if e.get("terrain") and biome in e["terrain"]}
    assert shown == set(BIOME_MINES[biome.lower()])


@pytest.mark.parametrize("biome", BIOMES)
def test_owner_sees_buy_and_sell_for_every_buildable_unit(biome):
    from app_core.economy.biome_buildings import BIOME_MINES

    html = render(location=biome)
    acts = _actions(html)
    expected = {e["unit"] for e in _catalog() if not e.get("terrain")} | set(BIOME_MINES[biome.lower()])
    for unit in expected:
        assert f"/buy/{unit}" in acts and f"/sell/{unit}" in acts, (biome, unit)
    # mines outside the biome must not be buyable
    for unit in {e["unit"] for e in _catalog() if e.get("terrain")} - set(BIOME_MINES[biome.lower()]):
        assert f"/buy/{unit}" not in acts, (biome, unit)


def test_distribution_centers_always_have_buy_and_sell():
    acts = _actions(render())
    assert "/buy/distribution_centers" in acts and "/sell/distribution_centers" in acts


def test_owner_page_has_four_labelled_tabs_and_unique_ids():
    html = render()
    for tab in ("overview", "buildings", "military", "resources"):
        assert f'id="tab-{tab}"' in html and f'id="ptab-{tab}"' in html
    ids = re.findall(r'\sid="([^"]+)"', html)
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, dupes


def test_every_building_quantity_input_has_a_label():
    html = render()
    for input_id in re.findall(r'<input[^>]*class="bld-qty[^"]*"[^>]*id="([^"]+)"', html):
        assert f'for="{input_id}"' in html, input_id


def test_visitor_sees_no_tabs_or_buy_forms():
    html = render(own=False)
    assert 'role="tablist"' not in html
    assert "formaction=" not in html
    assert "provincesettingsparent" not in html


def test_upgrade_names_and_images_follow_upgrades():
    html = render(upgrades={"onlineshopping": True, "highspeedrail": True})
    assert "Fulfillment Centers" in html and "Bullet Trains" in html
    plain = render()
    assert "Malls" in plain and "Monorails" in plain


def test_single_edit_entry_point_and_no_duplicate_picture_form():
    html = render()
    assert html.count('id="provinceEditToggle"') == 1
    assert html.count('name="province_image"') == 1


def test_page_has_no_per_building_header_sprawl():
    html = render()
    assert html.count("<h2") < 20 and html.count("<h3") < 90


def test_every_visible_form_control_is_labelled():
    html = render()
    for tag in re.findall(r"<(?:input|select)\b[^>]*>", html):
        if 'type="hidden"' in tag or 'type="file"' in tag:
            continue
        m = re.search(r'\sid="([^"]+)"', tag)
        labelled = "aria-label=" in tag or (m and f'for="{m.group(1)}"' in html)
        assert labelled, tag[:140]
