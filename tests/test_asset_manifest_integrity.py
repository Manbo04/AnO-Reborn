"""Ensure visual asset manifest paths are valid and fallback-ready."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parents[1]

from game_ui import game_asset_path, load_asset_manifest


def test_manifest_entries_have_legacy_and_path():
    manifest = load_asset_manifest()
    for bucket in ("buildings", "units", "resources", "biomes"):
        entries = manifest.get(bucket, {})
        assert entries, f"Manifest bucket {bucket} is empty"
        for key, row in entries.items():
            assert row.get("legacy"), f"{bucket}.{key} missing legacy fallback"
            assert row.get("path"), f"{bucket}.{key} missing override path"


def test_manifest_paths_exist_for_visual_overrides():
    manifest = load_asset_manifest()
    for bucket in ("buildings", "units", "resources", "biomes"):
        for key, row in manifest.get(bucket, {}).items():
            path = ROOT / "static" / row["path"]
            assert path.is_file(), f"Missing override file for {bucket}.{key}: {path}"


def test_game_asset_path_prefers_override_files():
    path = game_asset_path("buildings", "coal_burners")
    assert path.endswith(".svg")
    assert (ROOT / "static" / path).is_file()

    path = game_asset_path("units", "fighter_jets")
    assert path.endswith(".svg")
    assert (ROOT / "static" / path).is_file()

    path = game_asset_path("resources", "consumer_goods")
    assert path.endswith(".svg")
    assert (ROOT / "static" / path).is_file()
