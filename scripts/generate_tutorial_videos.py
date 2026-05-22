#!/usr/bin/env python3
"""
Generate short silent tutorial chapter videos from game screenshots.
Uses ffmpeg (Ken Burns + optional slideshow). Run from repo root:

    python3 scripts/generate_tutorial_videos.py

Output: static/tutorial/videos/chNN-*.mp4
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "static" / "images"
OUT = ROOT / "static" / "tutorial" / "videos"

W, H = 960, 540
FPS = 30
CRF = "28"

# Each chapter: output filename stem, image(s), on-screen captions (2-4s each)
CHAPTERS = [
    {
        "file": "ch01-welcome",
        "images": ["administrativebuilding.jpg"],
        "captions": [
            "Welcome to Affairs & Order",
            "The world runs on hourly ticks",
            "Tax, production, and population update automatically",
        ],
    },
    {
        "file": "ch02-provinces",
        "images": ["province.jpg", "administrativebuilding.jpg"],
        "captions": [
            "Provinces are your economic base",
            "Build infrastructure in each province",
            "More provinces cost more gold to acquire",
        ],
    },
    {
        "file": "ch03-resources",
        "images": ["coalmine.jpg", "bauxitemine.jpg", "aluminiumrefinery.jpg"],
        "captions": [
            "Mine raw materials first",
            "Refine into steel, aluminium, components",
            "Feed factories and your military",
        ],
    },
    {
        "file": "ch04-economy",
        "images": ["bank.jpg", "country.jpg"],
        "captions": [
            "Tax is your main gold source",
            "Consumer goods boost taxes +50%",
            "Missing rations or power cuts income",
        ],
    },
    {
        "file": "ch05-population",
        "images": ["washington.jpg", "bank.jpg"],
        "captions": [
            "Population needs rations to grow",
            "Distribute food and consumer goods",
            "Happiness and pollution affect growth",
        ],
    },
    {
        "file": "ch06-military",
        "images": ["military.jpg", "cruiser.jpg"],
        "captions": [
            "Recruit units with manpower and resources",
            "Attacks need 200+ supplies minimum",
            "Balance offense with economy",
        ],
    },
    {
        "file": "ch07-market",
        "images": ["market.jpg"],
        "captions": [
            "Player-driven global market",
            "Buy shortages, sell surpluses",
            "Check statistics before listing prices",
        ],
    },
    {
        "file": "ch08-upgrades",
        "images": ["upgrades.jpg", "advancedmachinery.jpg"],
        "captions": [
            "Permanent nation upgrades",
            "Military, economy, and supply bonuses",
            "Plan upgrades around your strategy",
        ],
    },
    {
        "file": "ch09-war",
        "images": ["war.jpg", "apache.jpg"],
        "captions": [
            "Declare war and choose unit counts",
            "Damage scales per unit, not all-or-nothing",
            "Coalition wars need coordination",
        ],
    },
    {
        "file": "ch10-coalitions",
        "images": ["coalition.jpg", "statistics.jpg"],
        "captions": [
            "Join coalitions for protection",
            "Shared banks and optional member tax",
            "Master economy, then compete globally",
        ],
    },
]


def run(cmd: list[str]) -> None:
    print(" ".join(cmd[:8]), "...")
    subprocess.run(cmd, check=True)


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def segment_duration(caption_count: int, total_sec: float = 14.0) -> float:
    return max(3.0, total_sec / caption_count)


def build_slideshow_video(ch: dict, out_path: Path) -> None:
    images = ch["images"]
    captions = ch["captions"]
    n = min(len(images), len(captions))
    if n == 0:
        raise ValueError(f"No content for {ch['file']}")

    seg = segment_duration(len(captions))
    frames = int(seg * FPS)
    parts: list[Path] = []
    tmp = OUT / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    for i in range(len(captions)):
        img_name = images[i % len(images)]
        img_path = IMG / img_name
        if not img_path.exists():
            raise FileNotFoundError(img_path)
        cap = escape_drawtext(captions[i])
        part = tmp / f"{ch['file']}_{i}.mp4"
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"zoompan=z='1.08':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
            f"d={frames}:s={W}x{H}:fps={FPS},"
            f"drawtext=text='{cap}':fontsize=28:fontcolor=white:"
            f"borderw=3:bordercolor=black@0.6:"
            f"x=(w-text_w)/2:y=h-90"
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(img_path),
                "-vf",
                vf,
                "-t",
                str(seg),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                CRF,
                "-an",
                str(part),
            ]
        )
        parts.append(part)

    list_file = tmp / f"{ch['file']}_list.txt"
    with list_file.open("w") as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")

    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_path),
        ]
    )

    for p in parts:
        p.unlink(missing_ok=True)
    list_file.unlink(missing_ok=True)


def main() -> int:
    if not shutil_which("ffmpeg"):
        print("ffmpeg not found", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for ch in CHAPTERS:
        out = OUT / f"{ch['file']}.mp4"
        print(f"Generating {out.name} ...")
        build_slideshow_video(ch, out)
        size_kb = out.stat().st_size // 1024
        print(f"  -> {size_kb} KB")

    # cleanup tmp dir if empty
    tmp = OUT / "_tmp"
    if tmp.exists() and not any(tmp.iterdir()):
        tmp.rmdir()

    print(f"Done. {len(CHAPTERS)} videos in {OUT}")
    return 0


def shutil_which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
