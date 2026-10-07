"""Offline check that game UI CSS is bundled into style.css."""
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parents[1]


def test_game_css_bundle_check_passes():
    script = ROOT / "scripts" / "check_game_css_bundle.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_mobile_embargo_and_recruitment_banner_rules_bundled():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".embargo-row .embargo-note" in css
    assert "background-size: contain" in css
    tpl = (ROOT / "templates" / "country_v2.html").read_text(encoding="utf-8")
    assert "embargo-row" in tpl and "embargo-note" in tpl
