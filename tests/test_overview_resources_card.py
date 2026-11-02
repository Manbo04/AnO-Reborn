from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "templates" / "country_v2.html").read_text()
LAYOUT = (ROOT / "templates" / "layout.html").read_text()


def test_overview_card_points_to_the_resources_panel_instead_of_duplicating_it():
    card = TEMPLATE[TEMPLATE.index('<div class="game-panel-title">Resources</div>'):]
    card = card[: card.index("Every amount is in the Resources panel")]
    assert 'onclick="resourcedivcontentshow()"' in card  # the way in
    assert "game-resource-chip" not in card  # no duplicated chip grid
    assert "game-meter" in card  # the unique food-reserves meter stays
    # ... and that panel exists on every page for the button to open
    assert 'id="resourcedivcontent"' in LAYOUT
    assert "function resourcedivcontentshow" in (ROOT / "static" / "script.js").read_text()
