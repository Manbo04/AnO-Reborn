#!/usr/bin/env python3
"""Generate building tooltip JSON from variables.py (single source of truth)."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import variables  # noqa: E402

OUT = os.path.join(ROOT, "static", "generated", "building_tooltips.json")


def _fmt_resource(key: str, val: int | float) -> str:
    label = "gold" if key == "money" else key.replace("_", " ")
    if isinstance(val, float):
        return f"{val:g} {label}"
    return f"{int(val):,} {label}"


def main() -> None:
    tooltips: dict[str, dict] = {}
    for name, data in variables.NEW_INFRA.items():
        plus = data.get("plus") or {}
        minus = data.get("convert_minus") or []
        produces = ", ".join(_fmt_resource(k, v) for k, v in plus.items() if v)
        consumes_parts = []
        for entry in minus:
            for k, v in entry.items():
                consumes_parts.append(_fmt_resource(k, v))
        consumes = ", ".join(consumes_parts)
        tooltips[name] = {
            "display_name": name.replace("_", " ").title(),
            "produces": produces or "—",
            "consumes": consumes or "—",
            "upkeep_gold": int(data.get("money") or 0),
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(tooltips, fh, indent=2)
    print(f"Wrote {len(tooltips)} building tooltips to {OUT}")


if __name__ == "__main__":
    main()
