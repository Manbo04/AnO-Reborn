#!/usr/bin/env python3
"""Generate static/asset-manifest.json from game_ui legacy mappings."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_ui import (  # noqa: E402
    BIOME_LEGACY_IMAGES,
    BUILDING_LEGACY_IMAGES,
    RESOURCE_LEGACY_IMAGES,
    UNIT_LEGACY_IMAGES,
)


def _building_path(key: str) -> str:
    for ext in (".svg", ".png"):
        rel = f"images/game/buildings/{key}{ext}"
        if (ROOT / "static" / rel).is_file():
            return rel
    return f"images/game/buildings/{key}.png"


def _unit_path(key: str) -> str:
    for ext in (".svg", ".png"):
        rel = f"images/game/units/{key}{ext}"
        if (ROOT / "static" / rel).is_file():
            return rel
    return f"images/game/units/{key}.png"


def main() -> None:
    manifest = {
        "version": 1,
        "note": "game/ paths are optional illustrated overrides; legacy used when missing",
        "buildings": {
            k: {"legacy": v, "path": _building_path(k)}
            for k, v in BUILDING_LEGACY_IMAGES.items()
        },
        "units": {
            k: {"legacy": v, "path": _unit_path(k)}
            for k, v in UNIT_LEGACY_IMAGES.items()
        },
        "resources": {
            k: {
                "legacy": v,
                "path": (
                    f"images/game/resources/{k}.svg"
                    if k in ("gold", "rations", "oil", "steel", "consumer_goods")
                    else f"images/game/resources/{k}.png"
                ),
            }
            for k, v in RESOURCE_LEGACY_IMAGES.items()
        },
        "biomes": {
            k: {"legacy": v, "path": f"images/game/biomes/{k.replace(' ', '_')}.jpg"}
            for k, v in BIOME_LEGACY_IMAGES.items()
        },
    }
    out = ROOT / "static" / "asset-manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(manifest['buildings'])} buildings)")


if __name__ == "__main__":
    main()
