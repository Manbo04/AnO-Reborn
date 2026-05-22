#!/usr/bin/env python3
"""Optional: create WebP siblings for images under static/images/ (requires Pillow)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "static" / "images"


def main() -> None:
    try:
        from PIL import Image
    except ImportError:
        print("Install Pillow: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    count = 0
    for path in IMAGES.rglob("*"):
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        out = path.with_suffix(".webp")
        if out.exists():
            continue
        try:
            Image.open(path).save(out, "WEBP", quality=82, method=4)
            count += 1
        except OSError as e:
            print(f"skip {path}: {e}")
    print(f"Created {count} webp files")


if __name__ == "__main__":
    main()
