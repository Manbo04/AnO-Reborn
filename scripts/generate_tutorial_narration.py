#!/usr/bin/env python3
"""
Generate TTS narration (MP3) and WebVTT captions for Nation Academy chapters.

Requires: pip install edge-tts
Run from repo root: python3 scripts/generate_tutorial_narration.py
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_PATH = ROOT / "static" / "tutorial" / "chapters.json"
AUDIO_DIR = ROOT / "static" / "tutorial" / "audio"
CAPTIONS_DIR = ROOT / "static" / "tutorial" / "captions"
VOICE = "en-US-GuyNeural"
DEFAULT_DURATION_SEC = 13.0


def load_chapters() -> list[dict]:
    data = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    return data["chapters"]


def vtt_timestamp(seconds: float) -> str:
    ms = int(max(0.0, seconds) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_part = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_part:03d}".replace(".", ",")


def write_vtt(stem: str, text: str, duration_sec: float) -> Path:
    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTIONS_DIR / f"{stem}.vtt"
    end = vtt_timestamp(duration_sec)
    body = (
        "WEBVTT\n\n"
        f"1\n00:00:00.000 --> {end}\n"
        f"{text.strip()}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def probe_duration_mp3(mp3: Path) -> float:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(mp3),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return DEFAULT_DURATION_SEC


async def generate_one(chapter: dict) -> None:
    import edge_tts

    stem = chapter["stem"]
    text = chapter["narration"]
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    mp3_path = AUDIO_DIR / f"{stem}.mp3"

    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(mp3_path))
    duration = probe_duration_mp3(mp3_path)
    write_vtt(stem, text, duration)
    print(f"  {stem}: {duration:.1f}s -> {mp3_path.name}")


async def main_async() -> int:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("Install edge-tts: pip install edge-tts", file=sys.stderr)
        return 1

    if not CHAPTERS_PATH.exists():
        print(f"Missing {CHAPTERS_PATH}", file=sys.stderr)
        return 1

    chapters = load_chapters()
    print(f"Generating narration for {len(chapters)} chapters...")
    for ch in chapters:
        await generate_one(ch)
    print(f"Done. Audio: {AUDIO_DIR}, captions: {CAPTIONS_DIR}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
