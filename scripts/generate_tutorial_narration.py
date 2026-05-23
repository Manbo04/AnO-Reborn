#!/usr/bin/env python3
"""
Generate per-step TTS narration for Nation Academy chapters.

Requires: pip install edge-tts
Run from repo root: python3 scripts/generate_tutorial_narration.py

Writes:
  static/tutorial/audio/{stem}_step_{nn}.mp3  (per step)
  static/tutorial/audio/{stem}.mp3            (concatenated)
  static/tutorial/captions/{stem}.vtt         (step-aligned)
  static/tutorial/step_durations.json         (audio lengths for recorder)
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tutorial_chapter_meta import effective_hold_sec  # noqa: E402

CHAPTERS_PATH = ROOT / "static" / "tutorial" / "chapters.json"
AUDIO_DIR = ROOT / "static" / "tutorial" / "audio"
CAPTIONS_DIR = ROOT / "static" / "tutorial" / "captions"
DURATIONS_PATH = ROOT / "static" / "tutorial" / "step_durations.json"

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "-12%"
PITCH = "+0Hz"


def load_chapters() -> list[dict]:
    data = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    return data["chapters"]


def vtt_timestamp(seconds: float) -> str:
    ms = int(max(0.0, seconds) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_part = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_part:03d}".replace(".", ",")


def probe_duration(path: Path) -> float:
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
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def narration_text(step: dict) -> str:
    text = (step.get("narration") or "").strip()
    if text:
        return text
    label = step.get("label", "")
    return re.sub(r"^\d+\.\s*", "", label).strip()


def concat_mp3s(parts: list[Path], out: Path) -> None:
    list_file = out.with_suffix(".concat.txt")
    with list_file.open("w") as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")
    subprocess.run(
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
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)


def write_step_vtt(stem: str, segments: list[tuple[str, float]]) -> Path:
    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTIONS_DIR / f"{stem}.vtt"
    lines = ["WEBVTT", ""]
    t = 0.0
    for i, (text, dur) in enumerate(segments, 1):
        start = vtt_timestamp(t)
        t += dur
        end = vtt_timestamp(t)
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def generate_step_mp3(text: str, out: Path) -> float:
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(str(out))
    return probe_duration(out)


async def generate_chapter(chapter: dict) -> list[float]:
    stem = chapter["stem"]
    steps = chapter.get("recording_steps") or []
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    part_paths: list[Path] = []
    vtt_segments: list[tuple[str, float]] = []
    hold_durations: list[float] = []

    for idx, step in enumerate(steps):
        text = narration_text(step)
        part = AUDIO_DIR / f"{stem}_step_{idx:02d}.mp3"
        duration = await generate_step_mp3(text, part)
        part_paths.append(part)
        vtt_segments.append((text, duration))
        hold = effective_hold_sec(step, duration)
        hold_durations.append(hold)
        print(f"    step {idx + 1}: {duration:.1f}s audio, {hold:.1f}s hold")

    combined = AUDIO_DIR / f"{stem}.mp3"
    concat_mp3s(part_paths, combined)
    write_step_vtt(stem, vtt_segments)
    total = probe_duration(combined)
    print(f"  {stem}: {total:.1f}s combined -> {combined.name}")
    return hold_durations


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
    all_holds: dict[str, list[float]] = {}

    print(f"Generating per-step narration for {len(chapters)} chapters...")
    for ch in chapters:
        print(f"  {ch['stem']}...")
        holds = await generate_chapter(ch)
        all_holds[ch["stem"]] = holds

    DURATIONS_PATH.write_text(
        json.dumps(all_holds, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote hold timings -> {DURATIONS_PATH}")
    print(f"Done. Audio: {AUDIO_DIR}, captions: {CAPTIONS_DIR}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
