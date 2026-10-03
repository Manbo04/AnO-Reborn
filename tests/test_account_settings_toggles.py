"""Offline tests verifying Dark Mode & Background Images toggles in account templates and bundle."""
from pathlib import Path
import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parents[1]


def test_account_v2_has_settings_toggles():
    tpl = (ROOT / "templates" / "account_v2.html").read_text(encoding="utf-8")
    assert 'id="slider"' in tpl
    assert 'onchange="toggleTheme()"' in tpl
    assert 'id="bgImagesToggle"' in tpl
    assert 'onchange="toggleBackgroundImages()"' in tpl
    assert "Dark Mode" in tpl
    assert "Background Images" in tpl
    assert "game-switch" in tpl
    assert "game-settings-list" in tpl


def test_account_v1_has_settings_toggles():
    tpl = (ROOT / "templates" / "account.html").read_text(encoding="utf-8")
    assert 'id="slider"' in tpl
    assert 'onchange="toggleTheme()"' in tpl
    assert 'id="bgImagesToggle"' in tpl
    assert 'onchange="toggleBackgroundImages()"' in tpl
    assert "Dark Mode" in tpl
    assert "Background Images" in tpl
    assert "game-switch" in tpl
    assert "game-settings-list" in tpl


def test_layout_head_has_early_preferences_init():
    layout = (ROOT / "templates" / "layout.html").read_text(encoding="utf-8")
    assert 'localStorage.getItem("ano_bg_images")' in layout
    assert 'localStorage.getItem("theme")' in layout
    assert "no-bg-images" in layout


def test_script_js_exports_background_functions():
    js = (ROOT / "static" / "script.js").read_text(encoding="utf-8")
    assert "function isBackgroundImagesEnabled()" in js
    assert "function setBackgroundImages(" in js
    assert "function toggleBackgroundImages()" in js
    assert "function toggleTheme()" in js
    assert "function setTheme(" in js
    assert "bgImagesToggle" in js
    assert "no-bg-images" in js


def test_bundled_css_contains_toggle_and_no_bg_rules():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert "html.no-bg-images .game-page-bg" in css
    assert "html.no-bg-images .game-page-overlay" in css
    assert ".game-switch" in css
    assert ".game-switch-slider" in css
    assert ".game-settings-list" in css
    assert ".game-setting-row" in css
