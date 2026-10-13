"""Static regression checks for frontend door-test fixes (no DB needed)."""
import re
from pathlib import Path

T = Path(__file__).resolve().parent.parent / "templates"


def _read(name):
    return (T / name).read_text(encoding="utf-8")


def test_nav_links_world_lore_war_board():
    s = _read("layout.html")
    for href in ("/world_map", "/lore_map", "/war-board"):
        assert f'href="{href}"' in s


def test_no_dead_coalition_types_link():
    assert "/coalition_types" not in _read("establish_coalition.html")


def test_country_pages_have_unique_a_ids():
    for name in ("country.html", "country_v2.html"):
        ids = re.findall(r'\bid="(a[1-5]|b[1-5])"', _read(name))
        assert len(ids) == len(set(ids)), name


def test_no_literal_none_leaks():
    assert "<td>None</td>" not in _read("coalition.html")
    assert "<td>None</td>" not in _read("mechanics/war.html")


def test_admin_live_feed_is_responsive():
    assert 'name="viewport"' in _read("admin_live_feed.html")


def test_hud_not_above_modals():
    assert "999999" not in _read("partials/game_hud.html")


def test_bond_edit_form_wired():
    assert 'action="/bonds/{{ b[0] }}/edit"' in _read("bonds_v2.html")


def test_res_images_have_fallback():
    assert "onerror" in _read("peace/peace_offers.html")
    for name in ("my_offers.html", "my_offers_v2.html"):
        for line in _read(name).splitlines():
            if "rescopper_plates" in line:
                assert "onerror" in line
