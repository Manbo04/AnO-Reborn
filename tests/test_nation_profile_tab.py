import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "templates" / "country_v2.html").read_text()


def test_profile_tab_is_wired_end_to_end():
    # nav item -> JS tab registry -> hidden/shown CSS -> content div
    assert 'id="countryprofile" onclick="countryprofile()"' in TEMPLATE
    assert 'id="profile"' in TEMPLATE
    assert '{ tab: "countryprofile", content: "profile" }' in (ROOT / "static" / "script.js").read_text()
    css = (ROOT / "static" / "style.css").read_text()
    assert re.search(r"\.profile,\s*\.revenue,", css)  # hidden by default
    assert re.search(r"\.profileclick,\s*\.revenueclick,", css)  # shown when active
    assert ".countryprofileclick" in css
    assert ".countryprofileclick" in (ROOT / "static" / "style.min.css").read_text()


def test_profile_blocks_rendered_once_per_viewer_type():
    # Owner sees them in the Profile tab, visitors inline in the View tab; never both.
    assert TEMPLATE.count("{{ profile_blocks() }}") == 2
    assert "{% if not status %}{{ profile_blocks() }}{% endif %}" in TEMPLATE
    tab = TEMPLATE[TEMPLATE.index('<div class="profile" id="profile">'):]
    assert tab.index("{{ profile_blocks() }}") < tab.index("<!--Revenue-->")
    assert TEMPLATE.index("{% macro profile_blocks() %}") < TEMPLATE.index("{{ profile_blocks() }}")


def test_moved_blocks_live_only_in_the_macro():
    macro = TEMPLATE[TEMPLATE.index("{% macro profile_blocks() %}"):TEMPLATE.index("{% endmacro %}")]
    for title in (">About<", ">National Profile<", "achievements"):
        assert title in macro
        assert TEMPLATE.count(title) == 1 or title == "achievements"
