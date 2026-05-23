#!/usr/bin/env python3
"""CI guard: bundled game UI rules must be present in static/style.css."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "static" / "style.css"
MARKER = "/* === GAME UI BUNDLE (auto-generated) === */"
REQUIRED_SELECTORS = (
    "province-map-node",
    ".game-hud",
    ".quick-link-card",
    "--game-space-md",
)


def main() -> int:
    if not STYLE.is_file():
        print(f"Missing {STYLE}", file=sys.stderr)
        return 1
    text = STYLE.read_text(encoding="utf-8")
    if MARKER not in text:
        print(f"Run: python3 scripts/bundle_game_css.py", file=sys.stderr)
        return 1
    missing = [s for s in REQUIRED_SELECTORS if s not in text]
    if missing:
        print(f"style.css missing bundled selectors: {missing}", file=sys.stderr)
        return 1
    print(f"OK: game UI bundle present ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
