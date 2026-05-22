#!/usr/bin/env python3
"""Append game UI CSS into style.css so production always serves one known file."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "static" / "style.css"
MARKER = "/* === GAME UI BUNDLE (auto-generated) === */"
FILES = [
    "static/css/tokens.css",
    "static/css/game-shell.css",
    "static/css/province-base.css",
    "static/css/game-experience.css",
    "static/css/game-country.css",
    "static/css/game-war.css",
]


def main() -> None:
    text = STYLE.read_text(encoding="utf-8")
    if MARKER in text:
        text = text.split(MARKER)[0].rstrip() + "\n"

    chunks = [MARKER, ""]
    for rel in FILES:
        path = ROOT / rel
        chunks.append(f"/* --- {rel} --- */")
        chunks.append(path.read_text(encoding="utf-8"))
        chunks.append("")

    STYLE.write_text(text + "\n" + "\n".join(chunks), encoding="utf-8")
    print(f"Bundled {len(FILES)} files into {STYLE}")


if __name__ == "__main__":
    main()
