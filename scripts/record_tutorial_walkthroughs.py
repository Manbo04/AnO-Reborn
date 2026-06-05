#!/usr/bin/env python3
"""
Record Nation Academy walkthroughs as slow, labeled in-game screen captures.

Each chapter follows recording_steps in static/tutorial/chapters.json:
  - Visit the correct page (and tab) for that lesson
  - Show an on-screen step banner
  - Hold for several seconds (no fast scrolling)
  - Build MP4 from screenshots (silent by default)

Requirements:
  pip install playwright psycopg2-binary bcrypt
  playwright install chromium
  ffmpeg on PATH

Run: python3 scripts/record_tutorial_walkthroughs.py --no-narration
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "tutorial" / "videos"
AUDIO_DIR = ROOT / "static" / "tutorial" / "audio"
CAPTIONS_DIR = ROOT / "static" / "tutorial" / "captions"
TMP_DIR = OUT_DIR / "_record_tmp"
CHAPTERS_PATH = ROOT / "static" / "tutorial" / "chapters.json"

VIDEO_W = 1280
VIDEO_H = 720
OUT_W = 960
OUT_H = 540
FPS = 30
DEFAULT_TMP_PW = "tutorial-record-2026"
DEFAULT_BASE = "https://affairsandorder.com"
TEST_UID = 16

BLOCKED_POST_FRAGMENTS = (
    "declare_war",
    "delete_own_account",
    "waramount",
    "warResult",
    "/market/buy",
    "/market/sell",
    "offer",
    "colBanks",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


def load_chapters() -> list[dict]:
    data = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    return data["chapters"]


def get_db_url() -> str:
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if url:
        return url
    return (
        "postgresql://postgres:yUhDEaGngcGPlRPrfqGIofVDwvRRXvcz@"
        "interchange.proxy.rlwy.net:41077/railway"
    )


def db_connect():
    import psycopg2

    parsed = urlparse(get_db_url())
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=(parsed.path[1:] if parsed.path else "postgres"),
    )


def backup_and_set_password(uid: int, tmp_pw: str) -> dict[str, Any]:
    import bcrypt

    backup: dict[str, Any] = {"hash": None, "password": None, "cols": set()}
    hashed = bcrypt.hashpw(tmp_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='users' AND column_name IN ('password','hash')"
        )
        cols = {r[0] for r in cur.fetchall()}
        backup["cols"] = cols
        if "hash" in cols:
            cur.execute("SELECT hash FROM users WHERE id=%s", (uid,))
            row = cur.fetchone()
            backup["hash"] = row[0] if row else None
            cur.execute("UPDATE users SET hash=%s WHERE id=%s", (hashed, uid))
        if "password" in cols:
            cur.execute("SELECT password FROM users WHERE id=%s", (uid,))
            row = cur.fetchone()
            backup["password"] = row[0] if row else None
            cur.execute(
                "UPDATE users SET password=%s WHERE id=%s",
                (hashed.encode("utf-8"), uid),
            )
        conn.commit()
    return backup


def restore_password(uid: int, backup: dict[str, Any]) -> None:
    cols = backup.get("cols") or set()
    with db_connect() as conn:
        cur = conn.cursor()
        if "hash" in cols:
            cur.execute("UPDATE users SET hash=%s WHERE id=%s", (backup.get("hash"), uid))
        if "password" in cols:
            cur.execute(
                "UPDATE users SET password=%s WHERE id=%s",
                (backup.get("password"), uid),
            )
        conn.commit()


def fetch_context(uid: int) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "username": "Tester of the Game",
        "province_id": None,
        "coalition_id": None,
        "user_id": uid,
    }
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT username FROM users WHERE id=%s", (uid,))
        row = cur.fetchone()
        if row and row[0]:
            ctx["username"] = row[0]
        cur.execute(
            "SELECT id FROM provinces WHERE userid=%s ORDER BY id ASC LIMIT 1",
            (uid,),
        )
        row = cur.fetchone()
        if row:
            ctx["province_id"] = row[0]
        cur.execute(
            "SELECT coalition_id FROM coalition_members WHERE user_id=%s LIMIT 1",
            (uid,),
        )
        row = cur.fetchone()
        if row:
            ctx["coalition_id"] = row[0]
    return ctx


def resolve_path(path: str, ctx: dict[str, Any]) -> str:
    pid = ctx.get("province_id") or ""
    return (
        path.replace("{province_id}", str(pid))
        .replace("{user_id}", str(ctx.get("user_id", "")))
        .replace("{coalition_id}", str(ctx.get("coalition_id") or ""))
    )


def guard_request(method: str, url: str) -> None:
    if method.upper() == "GET":
        return
    low = url.lower()
    if "/login" in low:
        return
    if any(f in low for f in BLOCKED_POST_FRAGMENTS):
        raise RuntimeError(f"Blocked non-GET during capture: {method} {url}")


async def browser_login(page, base: str, username: str, password: str) -> None:
    await page.goto(f"{base.rstrip('/')}/login", wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(1500)
    await page.fill('input[name="username"]', username)
    await page.fill('input[name="password"]', password)
    await page.evaluate("document.getElementById('login-form').submit()")
    await page.wait_for_load_state("domcontentloaded", timeout=90000)
    await page.wait_for_timeout(2500)


async def show_step_banner(page, chapter_title: str, step_label: str) -> None:
    await page.evaluate(
        """({ chapterTitle, stepLabel }) => {
            const id = 'ano-tutorial-rec-banner';
            let root = document.getElementById(id);
            if (!root) {
                root = document.createElement('div');
                root.id = id;
                root.style.cssText = [
                    'position:fixed', 'bottom:28px', 'left:50%', 'transform:translateX(-50%)',
                    'z-index:2147483647', 'max-width:min(920px,92vw)', 'padding:18px 28px',
                    'background:linear-gradient(135deg,rgba(8,20,32,0.96),rgba(0,55,75,0.96))',
                    'color:#fff', 'font-family:system-ui,sans-serif', 'text-align:center',
                    'border:3px solid #00a7e1', 'border-radius:14px',
                    'box-shadow:0 12px 40px rgba(0,0,0,0.55)', 'pointer-events:none'
                ].join(';');
                document.body.appendChild(root);
            }
            root.innerHTML = '<div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3fc;margin-bottom:8px;">'
                + chapterTitle + '</div><div style="font-size:22px;font-weight:800;line-height:1.35;">'
                + stepLabel + '</div>';
        }""",
        {"chapterTitle": chapter_title, "stepLabel": step_label},
    )


async def hide_step_banner(page) -> None:
    await page.evaluate(
        "() => { const el = document.getElementById('ano-tutorial-rec-banner'); if (el) el.remove(); }"
    )


async def click_tab(page, tab_id: str) -> None:
    await page.evaluate(
        f"""() => {{
            if (typeof {tab_id} === 'function') {{
                {tab_id}();
                return true;
            }}
            const el = document.getElementById('{tab_id}');
            if (el) {{ el.click(); return true; }}
            return false;
        }}"""
    )


async def gentle_scroll_to(page, selector: str) -> None:
    await page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
        }""",
        selector,
    )


def png_to_segment(png: Path, seconds: float, seg_out: Path) -> None:
    vf = (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=#0a0e14"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(png),
            "-vf",
            vf,
            "-t",
            str(seconds),
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "23",
            "-an",
            str(seg_out),
        ],
        check=True,
        capture_output=True,
    )


def concat_segments(segments: list[Path], mp4_out: Path) -> None:
    list_file = TMP_DIR / "concat_list.txt"
    with list_file.open("w") as f:
        for p in segments:
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
            "-movflags",
            "+faststart",
            str(mp4_out),
        ],
        check=True,
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)


def write_step_captions(chapter: dict, step_durations: list[tuple[str, float]]) -> None:
    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTIONS_DIR / f"{chapter['stem']}.vtt"
    lines = ["WEBVTT", ""]
    t = 0.0
    for i, (label, dur) in enumerate(step_durations, 1):
        start = _vtt_time(t)
        t += dur
        end = _vtt_time(t)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(label)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _vtt_time(seconds: float) -> str:
    ms = int(max(0.0, seconds) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_part = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_part:03d}".replace(".", ",")


def mux_narration(mp4_path: Path, stem: str) -> bool:
    mp3 = AUDIO_DIR / f"{stem}.mp3"
    if not mp3.exists():
        return False
    tmp_out = mp4_path.with_suffix(".mux.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp4_path),
            "-i",
            str(mp3),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(tmp_out),
        ],
        check=True,
        capture_output=True,
    )
    tmp_out.replace(mp4_path)
    return True


async def record_chapter_steps(
    page,
    base: str,
    chapter: dict,
    ctx: dict[str, Any],
    *,
    username: str,
    password: str,
    logged_in: bool,
) -> tuple[Path, bool]:
    stem = chapter["stem"]
    title = chapter["title"]
    steps = chapter.get("recording_steps") or []
    if not steps:
        raise ValueError(f"No recording_steps for {stem}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    work = TMP_DIR / stem
    work.mkdir(parents=True, exist_ok=True)

    segments: list[Path] = []
    caption_times: list[tuple[str, float]] = []
    session_logged_in = logged_in

    for idx, step in enumerate(steps):
        label = step["label"]
        hold = float(step.get("hold_sec", 6))
        path_tpl = resolve_path(step.get("path", "/country"), ctx)
        action = step.get("action")

        log(f"    step {idx + 1}/{len(steps)}: {label}")

        if action == "login":
            await page.goto(
                f"{base.rstrip('/')}/login",
                wait_until="domcontentloaded",
                timeout=90000,
            )
            await page.wait_for_timeout(2000)
            await show_step_banner(page, title, label)
            await page.wait_for_timeout(int(hold * 1000))
            png = work / f"step_{idx:02d}.png"
            await page.screenshot(path=str(png), type="png")
            seg = work / f"seg_{idx:02d}.mp4"
            png_to_segment(png, hold, seg)
            segments.append(seg)
            caption_times.append((label, hold))
            await hide_step_banner(page)
            await browser_login(page, base, username, password)
            session_logged_in = True
            continue

        if not session_logged_in:
            await browser_login(page, base, username, password)
            session_logged_in = True

        url = f"{base.rstrip('/')}{path_tpl}"
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(2500)

        tab = step.get("tab")
        if tab:
            await click_tab(page, tab)
            await page.wait_for_timeout(2000)

        scroll_sel = step.get("scroll")
        if scroll_sel:
            try:
                await gentle_scroll_to(page, scroll_sel)
                await page.wait_for_timeout(1200)
            except Exception:
                pass

        await show_step_banner(page, title, label)
        await page.wait_for_timeout(int(hold * 1000))

        png = work / f"step_{idx:02d}.png"
        await page.screenshot(path=str(png), type="png")
        await hide_step_banner(page)

        seg = work / f"seg_{idx:02d}.mp4"
        png_to_segment(png, hold, seg)
        segments.append(seg)
        caption_times.append((label, hold))

    mp4_out = OUT_DIR / f"{stem}.mp4"
    concat_segments(segments, mp4_out)
    write_step_captions(chapter, caption_times)

    for f in work.glob("*"):
        f.unlink()
    work.rmdir()

    return mp4_out, session_logged_in


async def main_async(
    chapter_filter: list[int] | None,
    *,
    with_narration: bool,
    narration_only: bool,
) -> int:
    chapters = load_chapters()
    stems = [c["stem"] for c in chapters]

    if narration_only:
        for ch in chapters:
            if chapter_filter is not None:
                i = chapters.index(ch)
                if i not in chapter_filter:
                    continue
            mp4 = OUT_DIR / f"{ch['stem']}.mp4"
            if mp4.exists() and with_narration:
                log(f"Mux narration into {ch['stem']} ...")
                mux_narration(mp4, ch["stem"])
        return 0

    if not which("ffmpeg"):
        log("ffmpeg not found")
        return 1

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("Install playwright: pip install playwright && playwright install chromium")
        return 1

    base = os.getenv("TUTORIAL_RECORD_BASE_URL", DEFAULT_BASE).rstrip("/")
    uid = int(os.getenv("TUTORIAL_RECORD_USER_ID", str(TEST_UID)))
    tmp_pw = os.getenv("TUTORIAL_RECORD_TMP_PASSWORD", DEFAULT_TMP_PW)
    skip_db = os.getenv("TUTORIAL_RECORD_SKIP_DB", "") == "1"

    username = os.getenv("TUTORIAL_RECORD_USERNAME", "")
    password = os.getenv("TUTORIAL_RECORD_PASSWORD", tmp_pw)
    pw_backup = None

    if not skip_db:
        log(f"Connecting to DB for user {uid}...")
        ctx = fetch_context(uid)
        username = username or ctx["username"]
        log(
            f"Recording as: {username!r} "
            f"(province={ctx['province_id']}, coalition={ctx['coalition_id']})"
        )
        pw_backup = backup_and_set_password(uid, tmp_pw)
        password = tmp_pw
    else:
        if not username:
            log("TUTORIAL_RECORD_SKIP_DB=1 requires TUTORIAL_RECORD_USERNAME")
            return 1
        ctx = fetch_context(uid)

    indices = chapter_filter if chapter_filter is not None else list(range(len(chapters)))

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": VIDEO_W, "height": VIDEO_H},
                locale="en-US",
            )
            context.on("request", lambda req: guard_request(req.method, req.url))
            page = await context.new_page()
            logged_in = False

            for i in indices:
                ch = chapters[i]
                log(f"Recording {ch['stem']} ({len(ch.get('recording_steps', []))} steps)...")
                mp4_path, logged_in = await record_chapter_steps(
                    page,
                    base,
                    ch,
                    ctx,
                    username=username,
                    password=password,
                    logged_in=logged_in,
                )
                if with_narration:
                    mux_narration(mp4_path, ch["stem"])
                size_kb = mp4_path.stat().st_size // 1024
                log(f"  -> {mp4_path.name} ({size_kb} KB)")

            await context.close()
            await browser.close()
    finally:
        if pw_backup is not None:
            log("Restoring original password...")
            restore_password(uid, pw_backup)

    total = sum(
        (OUT_DIR / s).stat().st_size for s in stems if (OUT_DIR / s).exists()
    )
    log(f"Done. Videos in {OUT_DIR} (total ~{total // 1024} KB)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", help="Comma-separated chapter numbers 1-10")
    parser.add_argument("--with-narration", action="store_true", help="Mux TTS audio (off by default)")
    parser.add_argument("--no-narration", action="store_true", help="Silent videos (default)")
    parser.add_argument("--narration-only", action="store_true", help="Only mux audio into existing MP4s")
    args = parser.parse_args()

    chapter_filter = None
    if args.chapters:
        chapter_filter = [int(x.strip()) - 1 for x in args.chapters.split(",")]

    with_narration = bool(args.with_narration) and not args.no_narration

    import asyncio

    return asyncio.run(
        main_async(
            chapter_filter,
            with_narration=with_narration,
            narration_only=args.narration_only,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
