"""Province demographics chart script guards deferred Chart.js load."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "static" / "province-demographics.js"


def test_province_demographics_js_exports_init_and_guards_chart():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "window.initProvinceDemographicsChart" in text
    assert "typeof Chart === 'undefined'" in text
    assert "Chart.getChart" in text
    assert "province-classic-view" in text
    assert "province-demographics-data" in text
    assert "addEventListener('load'" in text
