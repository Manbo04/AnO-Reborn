"""The Golden Throne / Holy Terra test feature was removed (2026-11-05). Keep it gone. DB-free."""
import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server
ROOT = Path(__file__).resolve().parent.parent


def test_traits_package_is_gone():
    assert not (ROOT / "app_core" / "traits").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app_core.traits")


def test_dawn_task_not_scheduled():
    schedule = (ROOT / "app_core" / "celery_schedule.py").read_text()
    tasks = (ROOT / "tasks.py").read_text()
    assert "task_nation_traits" not in schedule
    assert "task_nation_traits" not in tasks


@pytest.mark.parametrize(
    "rel",
    [
        "templates/country.html",
        "templates/country_v2.html",
        "templates/countries.html",
        "templates/countries_v2.html",
        "app.py",
        "countries.py",
        "static/style.css",
    ],
)
def test_no_throne_references(rel):
    text = (ROOT / rel).read_text().lower()
    for needle in ("golden_throne", "golden throne", "holy terra", "throne_card", "app_core.traits"):
        assert needle not in text, f"{needle} still referenced in {rel}"
