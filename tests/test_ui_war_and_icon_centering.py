from pathlib import Path
import pytest
from flask import Flask, render_template

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture
def app():
    app = Flask(
        "ano_test",
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["TESTING"] = True
    app.secret_key = "test-secret"

    @app.template_global()
    def game_asset_path(category, name):
        return f"images/{category}/{name}.png"

    @app.template_filter()
    def fmt(val):
        try:
            return f"{int(val):,}"
        except Exception:
            return str(val)

    @app.template_filter()
    def weight_fmt(val):
        try:
            return f"{float(val):,.1f}t"
        except Exception:
            return str(val)

    return app


def test_war_v2_attacker_rendering(app):
    with app.test_request_context("/war/77"):
        html = render_template(
            "war_v2.html",
            attacker="10",
            attacker_name="Gondor",
            defender="20",
            defender_name="Mordor",
            cId_type="attacker",
            war_id=77,
            attacker_info={"morale": 90, "supplies": 1500},
            defender_info={"morale": 35, "supplies": 400},
            peace_to_send=20,
            spyCount=12,
        )

        # Confrontation panel structure
        assert "war-matchup-panel" in html
        assert "war-combatant-flag" in html
        assert "war-flag-wrap" in html
        assert "war-vs-badge" in html
        assert "VS" in html

        # Role badges & names
        assert "Gondor" in html
        assert "Mordor" in html
        assert 'Attacker <span class="war-role-you">(You)</span>' in html
        assert "war-role-badge--def" in html

        # Stats display
        assert "90 / 100 Morale" in html
        assert "35 / 100 Morale" in html
        assert "1500 / 2000 Supplies" in html
        assert "400 / 2000 Supplies" in html

        # Action attack button
        assert 'href="/war/77/attack"' in html
        assert "Attack" in html

        # Espionage form
        assert 'action="/spyResult"' in html
        assert 'name="spy_type"' in html
        assert 'name="spies"' in html

        # Peace offer form
        assert 'action="/send_peace_offer/77/20"' in html
        assert 'name="money"' in html
        assert 'name="ammunition"' in html

        # Broken layout classes absent
        assert "card-align-row" not in html


def test_war_v2_defender_rendering(app):
    with app.test_request_context("/war/77"):
        html = render_template(
            "war_v2.html",
            attacker="10",
            attacker_name="Gondor",
            defender="20",
            defender_name="Mordor",
            cId_type="defender",
            war_id=77,
            attacker_info={"morale": 90, "supplies": 1500},
            defender_info={"morale": 35, "supplies": 400},
            peace_to_send=10,
            spyCount=5,
        )

        assert "war-matchup-panel" in html
        assert 'Defender <span class="war-role-you">(You)</span>' in html
        assert "war-role-badge--atk" in html
        assert 'action="/send_peace_offer/77/10"' in html
        assert "card-align-row" not in html


def test_war_classic_no_stretch(app):
    with app.test_request_context("/war/77"):
        html = render_template(
            "war.html",
            attacker="10",
            attacker_name="Gondor",
            defender="20",
            defender_name="Mordor",
            cId_type="defender",
            war_id=77,
            attacker_info={"morale": 90, "supplies": 1500},
            defender_info={"morale": 35, "supplies": 400},
            peace_to_send=10,
            spyCount=5,
        )
        assert "card-align-row" not in html
        assert "35 / 100 Morale" in html
        assert "90 / 100 Morale" in html


def test_resourcediv_layout_geometry():
    from pathlib import Path

    layout_file = Path("templates/layout.html")
    assert layout_file.exists()
    content = layout_file.read_text(encoding="utf-8")
    assert 'top: 150px' not in content, "Hardcoded top: 150px must be removed from layout.html"
    assert 'id="resourcediv"' in content
    assert 'class="resourcediv"' in content


def test_css_bundle_contains_all_rules():
    from pathlib import Path

    style_file = Path("static/style.css")
    assert style_file.exists()
    css = style_file.read_text(encoding="utf-8")

    assert ".war-matchup-panel" in css
    assert ".war-combatant-flag" in css
    assert ".war-vs-badge" in css
    assert ".war-vs-text" in css
    assert ".war-role-badge--atk" in css
    assert ".war-role-badge--def" in css
    assert ".resourcediv" in css


SPECTATOR_CTX = dict(
    attacker="10",
    attacker_name="Gondor",
    defender="20",
    defender_name="Mordor",
    cId_type="spectator",
    war_id=77,
    war_type="Raze",
    agressor_message="",
    attacker_info={"morale": 90, "supplies": 1500},
    defender_info={"morale": 35, "supplies": 400},
)


@pytest.mark.parametrize("template", ["war_v2.html", "war.html"])
def test_war_spectator_is_read_only(app, template):
    with app.test_request_context("/war/77"):
        html = render_template(template, **SPECTATOR_CTX)

    assert "Gondor" in html and "Mordor" in html
    assert "90 / 100 Morale" in html or "90 / 100 Morale" in html.replace("\n", "")
    assert "spectator" in html
    assert "/warchoose/77" not in html
    assert "/spyResult" not in html
    assert "/send_peace_offer" not in html


def test_wars_v2_lists_world_wars(app):
    with app.test_request_context("/wars"):
        html = render_template(
            "wars_v2.html",
            units={},
            warsCount=0,
            war_info={},
            yourCountry="Rohan",
            current_defense=[],
            joinable_wars=[],
            world_wars=[
                {
                    "id": 5,
                    "att": {"id": 1, "name": "Gondor", "morale": 80},
                    "def": {"id": 2, "name": "Mordor", "morale": 20},
                }
            ],
        )

    assert 'id="world-wars"' in html
    assert 'href="/war/5"' in html
    assert "Gondor" in html and "Mordor" in html
