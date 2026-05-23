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
