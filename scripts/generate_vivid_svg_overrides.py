#!/usr/bin/env python3
"""Generate vivid SVG override assets for resources, buildings, and units.

These assets preserve existing UI geometry while replacing visuals only.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_ui import (
    BIOME_LEGACY_IMAGES,
    BUILDING_LEGACY_IMAGES,
    RESOURCE_LEGACY_IMAGES,
    UNIT_LEGACY_IMAGES,
)

STATIC = ROOT / "static" / "images" / "game"
RES_DIR = STATIC / "resources"
BLD_DIR = STATIC / "buildings"
UNIT_DIR = STATIC / "units"
BIOME_DIR = STATIC / "biomes"


RESOURCE_SYMBOLS = {
    "gold": "$",
    "money": "$",
    "rations": "R",
    "oil": "O",
    "coal": "C",
    "uranium": "U",
    "bauxite": "B",
    "iron": "Fe",
    "lead": "Pb",
    "copper": "Cu",
    "lumber": "L",
    "components": "CP",
    "steel": "St",
    "consumer_goods": "CG",
    "aluminium": "Al",
    "gasoline": "G",
    "ammunition": "A",
}

RESOURCE_COLORS = {
    "gold": ("#f7c847", "#b87e16"),
    "money": ("#f7c847", "#b87e16"),
    "rations": ("#79d7ff", "#2c79b6"),
    "oil": ("#6f7b8a", "#26313f"),
    "coal": ("#9aa3ad", "#2f3740"),
    "uranium": ("#7ef39f", "#1f8c56"),
    "bauxite": ("#e49a62", "#944b2e"),
    "iron": ("#d7b0a7", "#8a554a"),
    "lead": ("#b8aeca", "#6d6382"),
    "copper": ("#f29a63", "#995037"),
    "lumber": ("#d4ab6a", "#84572c"),
    "components": ("#8bd4ff", "#3276aa"),
    "steel": ("#c2d4e6", "#5f748a"),
    "consumer_goods": ("#f4c6ff", "#9b5fc2"),
    "aluminium": ("#d9e2f2", "#7f8fa3"),
    "gasoline": ("#f7b964", "#a06416"),
    "ammunition": ("#ff9d80", "#b34b35"),
}


def _slug_gradient(key: str) -> tuple[str, str]:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    hue = int(digest[:2], 16) % 360
    return (
        f"hsl({hue} 82% 66%)",
        f"hsl({(hue + 35) % 360} 68% 35%)",
    )


def _resource_svg(key: str) -> str:
    symbol = RESOURCE_SYMBOLS.get(key, key[:2].upper())
    c1, c2 = RESOURCE_COLORS.get(key, _slug_gradient(key))
    fs = 20 if len(symbol) <= 2 else 15
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{key}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <radialGradient id="r" cx="30%" cy="25%" r="60%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.5)"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
    </radialGradient>
  </defs>
  <rect x="4" y="4" width="56" height="56" rx="14" fill="url(#g)" stroke="rgba(15,23,42,0.55)" stroke-width="2.8"/>
  <rect x="8" y="8" width="48" height="48" rx="11" fill="url(#r)"/>
  <text x="32" y="39" text-anchor="middle" font-size="{fs}" font-family="Roboto,sans-serif" fill="#f8fafc" font-weight="700">{symbol}</text>
</svg>
"""


def _card_svg(key: str, kind: str) -> str:
    c1, c2 = _slug_gradient(f"{kind}:{key}")
    label = key.replace("_", " ").title()
    initials = "".join([w[0] for w in label.split()[:2]]).upper() or "A"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-label="{label}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="rgba(255,255,255,0.3)"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0.15)"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="26" fill="url(#bg)"/>
  <circle cx="206" cy="48" r="28" fill="rgba(255,255,255,0.2)"/>
  <rect x="22" y="22" width="212" height="212" rx="20" fill="url(#panel)" stroke="rgba(15,23,42,0.35)" stroke-width="3"/>
  <text x="128" y="134" text-anchor="middle" font-size="56" font-family="Roboto,sans-serif" fill="rgba(248,250,252,0.95)" font-weight="700">{initials}</text>
  <rect x="24" y="186" width="208" height="44" rx="12" fill="rgba(15,23,42,0.4)"/>
  <text x="128" y="214" text-anchor="middle" font-size="16" font-family="Roboto,sans-serif" fill="#f8fafc" font-weight="600">{label}</text>
</svg>
"""


def _biome_svg(key: str) -> str:
    c1, c2 = _slug_gradient(f"biome:{key}")
    label = key.replace("_", " ").title()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 768" role="img" aria-label="{label}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
    <linearGradient id="land" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c2}"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="768" fill="url(#sky)"/>
  <ellipse cx="512" cy="620" rx="620" ry="210" fill="url(#land)" opacity="0.88"/>
  <ellipse cx="220" cy="170" rx="150" ry="48" fill="rgba(255,255,255,0.25)"/>
  <ellipse cx="760" cy="230" rx="190" ry="58" fill="rgba(255,255,255,0.18)"/>
  <rect x="48" y="46" width="360" height="64" rx="20" fill="rgba(15,23,42,0.35)"/>
  <text x="228" y="88" text-anchor="middle" font-size="34" font-family="Roboto,sans-serif" fill="#f8fafc" font-weight="700">{label}</text>
</svg>
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    for key in RESOURCE_LEGACY_IMAGES:
        _write(RES_DIR / f"{key}.svg", _resource_svg(key))

    for key in BUILDING_LEGACY_IMAGES:
        _write(BLD_DIR / f"{key}.svg", _card_svg(key, "building"))

    for key in UNIT_LEGACY_IMAGES:
        _write(UNIT_DIR / f"{key}.svg", _card_svg(key, "unit"))

    for key in BIOME_LEGACY_IMAGES:
        slug = key.replace(" ", "_")
        _write(BIOME_DIR / f"{slug}.svg", _biome_svg(key))

    print(
        f"Generated {len(RESOURCE_LEGACY_IMAGES)} resource, "
        f"{len(BUILDING_LEGACY_IMAGES)} building, and "
        f"{len(UNIT_LEGACY_IMAGES)} unit SVG overrides, plus "
        f"{len(BIOME_LEGACY_IMAGES)} biome backdrops."
    )


if __name__ == "__main__":
    main()
