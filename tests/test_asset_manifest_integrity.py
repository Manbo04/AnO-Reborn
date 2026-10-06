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


def test_every_game_asset_resolves_to_an_existing_image():
    """What players see: game_asset_path() must always land on a real file.

    The illustrated game/ overrides are optional (the SVG set was removed on
    purpose in 84de070a), so a missing override is fine as long as the
    legacy image it falls back to exists.
    """
    manifest = load_asset_manifest()
    missing = []
    for bucket in ("buildings", "units", "resources", "biomes"):
        for key in manifest.get(bucket, {}):
            rel = game_asset_path(bucket, key)
            if not (ROOT / "static" / rel).is_file():
                missing.append(f"{bucket}.{key} -> static/{rel}")
    assert not missing, "Broken game images:\n" + "\n".join(missing)
