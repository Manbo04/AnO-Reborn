#!/usr/bin/env python3
"""Generate an exhaustive visual-asset inventory with usage frequency.

Outputs:
  - docs/visual_asset_inventory.json

Inventory dimensions:
  1) Known assets from game_ui mapping dictionaries and asset-manifest.json
  2) Direct template/static CSS references (images/* and /flag/*)
  3) Per-file usage counts for each discovered reference
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_ui import (  # noqa: E402
    BIOME_LEGACY_IMAGES,
    BUILDING_LEGACY_IMAGES,
    RESOURCE_LEGACY_IMAGES,
    UNIT_LEGACY_IMAGES,
)

TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUT_PATH = ROOT / "docs" / "visual_asset_inventory.json"

IMG_LITERAL_RE = re.compile(r"""images/[A-Za-z0-9_\-/\.]+""")
CSS_URL_RE = re.compile(r"""url\(["']?(images/[A-Za-z0-9_\-/\.]+)["']?\)""")
FLAG_RE = re.compile(r"""/flag/(?:country|coalition)/[A-Za-z0-9_\-{}]+""")
GAME_ASSET_PATH_RE = re.compile(
    r"""game_asset_path\(\s*['"](?P<kind>resources|buildings|units|biomes)['"]\s*,\s*(?P<key>[^)]+)\)"""
)


def _iter_files() -> list[Path]:
    out: list[Path] = []
    out.extend(TEMPLATES_DIR.rglob("*.html"))
    out.extend((STATIC_DIR / "css").rglob("*.css"))
    out.append(STATIC_DIR / "style.css")
    return [p for p in out if p.is_file()]


def _safe_rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _known_assets() -> dict:
    manifest = json.loads((STATIC_DIR / "asset-manifest.json").read_text(encoding="utf-8"))
    return {
        "mapping_keys": {
            "buildings": sorted(BUILDING_LEGACY_IMAGES.keys()),
            "units": sorted(UNIT_LEGACY_IMAGES.keys()),
            "resources": sorted(RESOURCE_LEGACY_IMAGES.keys()),
            "biomes": sorted(BIOME_LEGACY_IMAGES.keys()),
        },
        "manifest_paths": {
            "buildings": {
                k: v["path"] for k, v in manifest.get("buildings", {}).items()
            },
            "units": {
                k: v["path"] for k, v in manifest.get("units", {}).items()
            },
            "resources": {
                k: v["path"] for k, v in manifest.get("resources", {}).items()
            },
            "biomes": {
                k: v["path"] for k, v in manifest.get("biomes", {}).items()
            },
        },
    }


def _discover_references() -> dict:
    ref_counter: Counter[str] = Counter()
    per_file: dict[str, Counter[str]] = defaultdict(Counter)
    dynamic_calls: dict[str, list[dict[str, str]]] = defaultdict(list)

    for path in _iter_files():
        rel = _safe_rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")

        for m in IMG_LITERAL_RE.finditer(text):
            token = m.group(0)
            ref_counter[token] += 1
            per_file[rel][token] += 1

        for m in CSS_URL_RE.finditer(text):
            token = m.group(1)
            ref_counter[token] += 1
            per_file[rel][token] += 1

        for m in FLAG_RE.finditer(text):
            token = m.group(0)
            ref_counter[token] += 1
            per_file[rel][token] += 1

        for m in GAME_ASSET_PATH_RE.finditer(text):
            kind = m.group("kind")
            key_expr = m.group("key").strip()
            dynamic_calls[rel].append({"kind": kind, "key_expr": key_expr})

    refs_sorted = sorted(ref_counter.items(), key=lambda x: (-x[1], x[0]))
    per_file_out = {
        path: sorted(counter.items(), key=lambda x: (-x[1], x[0]))
        for path, counter in sorted(per_file.items())
        if counter
    }
    dynamic_out = {k: v for k, v in sorted(dynamic_calls.items()) if v}

    return {
        "top_references": refs_sorted,
        "per_file_references": per_file_out,
        "dynamic_game_asset_calls": dynamic_out,
    }


def main() -> None:
    payload = {
        "generated_from_commit": None,
        "known_assets": _known_assets(),
        "discovered_usage": _discover_references(),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
