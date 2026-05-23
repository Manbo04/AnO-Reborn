#!/usr/bin/env python3
"""
Record Nation Academy walkthroughs as in-game screen video with smooth cursor motion.

Each chapter follows recording_steps in static/tutorial/chapters.json:
  - Playwright record_video per chapter
  - Smooth mouse moves and tab clicks
  - On-screen step banner with tab chips
  - Optional per-chapter TTS mux

Requirements:
  pip install playwright psycopg2-binary bcrypt
  playwright install chromium
  ffmpeg on PATH

Run:
  python3 scripts/generate_tutorial_narration.py
  python3 scripts/record_tutorial_walkthroughs.py --with-narration
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tutorial_chapter_meta import (  # noqa: E402
    chips_for_step,
    effective_hold_sec,
)

OUT_DIR = ROOT / "static" / "tutorial" / "videos"
AUDIO_DIR = ROOT / "static" / "tutorial" / "audio"
CAPTIONS_DIR = ROOT / "static" / "tutorial" / "captions"
DURATIONS_PATH = ROOT / "static" / "tutorial" / "step_durations.json"
TMP_DIR = OUT_DIR / "_record_tmp"
CHAPTERS_PATH = ROOT / "static" / "tutorial" / "chapters.json"

VIDEO_W = 1280
VIDEO_H = 720
OUT_W = 960
OUT_H = 540
VIDEO_CRF = 26
DEFAULT_TMP_PW = "tutorial-record-2026"
DEFAULT_BASE = "https://affairsandorder.com"
TEST_UID = 16
MOUSE_STEPS = 35

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


def load_step_durations() -> dict[str, list[float]]:
    if not DURATIONS_PATH.exists():
        return {}
    return json.loads(DURATIONS_PATH.read_text(encoding="utf-8"))


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


async def inject_cursor_overlay(page) -> None:
    await page.evaluate(
        """() => {
            if (document.getElementById('ano-tutorial-cursor')) return;
            const dot = document.createElement('div');
            dot.id = 'ano-tutorial-cursor';
            dot.style.cssText = [
                'position:fixed', 'width:22px', 'height:22px', 'border-radius:50%',
                'border:3px solid #fff', 'background:rgba(0,167,225,0.85)',
                'box-shadow:0 0 12px rgba(0,167,225,0.9), 0 2px 8px rgba(0,0,0,0.5)',
                'z-index:2147483646', 'pointer-events:none', 'transform:translate(-50%,-50%)',
                'left:0px', 'top:0px', 'transition:none'
            ].join(';');
            document.body.appendChild(dot);
        }"""
    )


async def move_cursor_overlay(page, x: float, y: float) -> None:
    await page.evaluate(
        """({ x, y }) => {
            const dot = document.getElementById('ano-tutorial-cursor');
            if (dot) { dot.style.left = x + 'px'; dot.style.top = y + 'px'; }
        }""",
        {"x": x, "y": y},
    )


async def smooth_move(page, x: float, y: float, *, steps: int = MOUSE_STEPS) -> None:
    pos = await page.evaluate(
        """() => {
            const dot = document.getElementById('ano-tutorial-cursor');
            if (dot) {
                return { x: parseFloat(dot.style.left) || 640, y: parseFloat(dot.style.top) || 360 };
            }
            return { x: 640, y: 360 };
        }"""
    )
    sx, sy = float(pos["x"]), float(pos["y"])
    for i in range(1, steps + 1):
        t = i / steps
        cx = sx + (x - sx) * t
        cy = sy + (y - sy) * t
        await page.mouse.move(cx, cy)
        await move_cursor_overlay(page, cx, cy)
        await page.wait_for_timeout(12)


async def smooth_click_locator(page, locator, *, steps: int = MOUSE_STEPS) -> bool:
    try:
        await locator.wait_for(state="visible", timeout=15000)
        box = await locator.bounding_box()
        if not box:
            return False
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        await smooth_move(page, x, y, steps=steps)
        await page.mouse.down()
        await page.wait_for_timeout(80)
        await page.mouse.up()
        await page.wait_for_timeout(400)
        return True
    except Exception:
        return False


async def smooth_click_selector(page, selector: str) -> bool:
    loc = page.locator(selector).first
    return await smooth_click_locator(page, loc)


async def click_tab_smooth(page, tab_id: str) -> None:
    clicked = await smooth_click_selector(page, f"#{tab_id}")
    if not clicked:
        await page.evaluate(
            f"""() => {{
                if (typeof {tab_id} === 'function') {tab_id}();
                else {{
                    const el = document.getElementById('{tab_id}');
                    if (el) el.click();
                }}
            }}"""
        )
        await page.wait_for_timeout(800)


async def show_step_banner(
    page,
    chapter_title: str,
    step_label: str,
    step: dict[str, Any],
) -> None:
    chips = chips_for_step(step)
    active_tab = step.get("tab")
    chip_data = [{"id": tid, "label": lbl} for tid, lbl in chips]
    await page.evaluate(
        """({ chapterTitle, stepLabel, chips, activeTab }) => {
            const id = 'ano-tutorial-rec-banner';
            let root = document.getElementById(id);
            if (!root) {
                root = document.createElement('div');
                root.id = id;
                root.style.cssText = [
                    'position:fixed', 'bottom:28px', 'left:50%', 'transform:translateX(-50%)',
                    'z-index:2147483647', 'max-width:min(920px,92vw)', 'padding:18px 28px 14px',
                    'background:linear-gradient(135deg,rgba(8,20,32,0.96),rgba(0,55,75,0.96))',
                    'color:#fff', 'font-family:system-ui,sans-serif', 'text-align:center',
                    'border:3px solid #00a7e1', 'border-radius:14px',
                    'box-shadow:0 12px 40px rgba(0,0,0,0.55)', 'pointer-events:none'
                ].join(';');
                document.body.appendChild(root);
            }
            let chipsHtml = '';
            if (chips && chips.length) {
                chipsHtml = '<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:14px;">'
                    + chips.map(c => {
                        const on = c.id === activeTab;
                        const bg = on ? '#00a7e1' : 'rgba(255,255,255,0.12)';
                        const col = on ? '#0a0e14' : '#e2e8f0';
                        const wt = on ? '800' : '600';
                        return '<span style="padding:6px 14px;border-radius:8px;font-size:13px;font-weight:'
                            + wt + ';background:' + bg + ';color:' + col + ';border:1px solid '
                            + (on ? '#00a7e1' : 'rgba(255,255,255,0.25)') + ';">' + c.label + '</span>';
                    }).join('') + '</div>';
            }
            root.innerHTML = '<div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3fc;margin-bottom:8px;">'
                + chapterTitle + '</div><div style="font-size:22px;font-weight:800;line-height:1.35;">'
                + stepLabel + '</div>' + chipsHtml;
        }""",
        {
            "chapterTitle": chapter_title,
            "stepLabel": step_label,
            "chips": chip_data,
            "activeTab": active_tab,
        },
    )


async def hide_step_banner(page) -> None:
    await page.evaluate(
        "() => { const el = document.getElementById('ano-tutorial-rec-banner'); if (el) el.remove(); }"
    )


async def smooth_scroll_to(page, selector: str) -> None:
    await page.evaluate(
        """async (sel) => {
            const el = document.querySelector(sel);
            if (!el) return;
            const target = el.getBoundingClientRect().top + window.scrollY - 120;
            const start = window.scrollY;
            const dist = target - start;
            const steps = 24;
            for (let i = 1; i <= steps; i++) {
                window.scrollTo(0, start + dist * (i / steps));
                await new Promise(r => setTimeout(r, 40));
            }
        }""",
        selector,
    )


async def browser_login_smooth(page, base: str, username: str, password: str) -> None:
    await page.goto(f"{base.rstrip('/')}/login", wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(1500)
    await inject_cursor_overlay(page)
    user_loc = page.locator('input[name="username"]')
    pass_loc = page.locator('input[name="password"]')
    await smooth_click_locator(page, user_loc)
    await user_loc.fill(username)
    await smooth_click_locator(page, pass_loc)
    await pass_loc.fill(password)
    submit = page.locator("#login-form button[type='submit'], #login-form input[type='submit']").first
    if await submit.count() > 0:
        await smooth_click_locator(page, submit)
    else:
        await page.evaluate("document.getElementById('login-form').submit()")
    await page.wait_for_load_state("domcontentloaded", timeout=90000)
    await page.wait_for_timeout(2500)
    await inject_cursor_overlay(page)


def webm_to_mp4(webm: Path, mp4_out: Path) -> None:
    vf = (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=#0a0e14"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(webm),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            str(VIDEO_CRF),
            "-preset",
            "medium",
            "-an",
            "-movflags",
            "+faststart",
            str(mp4_out),
        ],
        check=True,
        capture_output=True,
    )


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


def pad_audio_to_duration(mp3: Path, target_sec: float, padded: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp3),
            "-af",
            f"apad=pad_dur={max(0.0, target_sec):.3f}",
            "-t",
            f"{target_sec:.3f}",
            str(padded),
        ],
        check=True,
        capture_output=True,
    )


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


def mux_narration(mp4_path: Path, stem: str) -> bool:
    mp3 = AUDIO_DIR / f"{stem}.mp3"
    if not mp3.exists():
        return False
    video_dur = probe_duration(mp4_path)
    audio_dur = probe_duration(mp3)
    padded = AUDIO_DIR / f"{stem}.padded.mp3"
    if video_dur > 0 and audio_dur < video_dur - 0.05:
        pad_audio_to_duration(mp3, video_dur, padded)
        audio_in = padded
    else:
        audio_in = mp3
    tmp_out = mp4_path.with_suffix(".mux.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp4_path),
            "-i",
            str(audio_in),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-movflags",
            "+faststart",
            str(tmp_out),
        ],
        check=True,
        capture_output=True,
    )
    tmp_out.replace(mp4_path)
    padded.unlink(missing_ok=True)
    return True


def find_recorded_webm(work_dir: Path) -> Path | None:
    webms = sorted(work_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    return webms[0] if webms else None


async def record_chapter_video(
    browser,
    base: str,
    chapter: dict,
    ctx: dict[str, Any],
    *,
    username: str,
    password: str,
    logged_in: bool,
    step_audio_durations: list[float] | None,
) -> tuple[Path, bool]:
    stem = chapter["stem"]
    title = chapter["title"]
    steps = chapter.get("recording_steps") or []
    if not steps:
        raise ValueError(f"No recording_steps for {stem}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    work = TMP_DIR / stem
    if work.exists():
        for f in work.glob("*"):
            f.unlink()
    work.mkdir(parents=True, exist_ok=True)

    caption_times: list[tuple[str, float]] = []
    session_logged_in = logged_in

    context = await browser.new_context(
        viewport={"width": VIDEO_W, "height": VIDEO_H},
        locale="en-US",
        record_video_dir=str(work),
        record_video_size={"width": VIDEO_W, "height": VIDEO_H},
    )
    context.on("request", lambda req: guard_request(req.method, req.url))
    page = await context.new_page()
    await inject_cursor_overlay(page)

    last_path: str | None = None

    for idx, step in enumerate(steps):
        label = step["label"]
        audio_dur = None
        if step_audio_durations and idx < len(step_audio_durations):
            audio_dur = step_audio_durations[idx]
        hold = effective_hold_sec(step, audio_dur)
        path_tpl = resolve_path(step.get("path", "/country"), ctx)
        action = step.get("action")

        log(f"    step {idx + 1}/{len(steps)}: {label} ({hold:.1f}s)")

        if action == "login":
            await page.goto(
                f"{base.rstrip('/')}/login",
                wait_until="domcontentloaded",
                timeout=90000,
            )
            await page.wait_for_timeout(2000)
            await inject_cursor_overlay(page)
            await show_step_banner(page, title, label, step)
            await page.wait_for_timeout(int(hold * 1000))
            await hide_step_banner(page)
            await browser_login_smooth(page, base, username, password)
            session_logged_in = True
            caption_times.append((label, hold))
            last_path = path_tpl
            continue

        if not session_logged_in:
            await browser_login_smooth(page, base, username, password)
            session_logged_in = True

        url = f"{base.rstrip('/')}{path_tpl}"
        if path_tpl != last_path:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(2000)
            await inject_cursor_overlay(page)
            last_path = path_tpl
        else:
            await page.wait_for_timeout(600)

        tab = step.get("tab")
        if tab:
            await click_tab_smooth(page, tab)
            await page.wait_for_timeout(1200)

        scroll_sel = step.get("scroll")
        if scroll_sel:
            try:
                await smooth_scroll_to(page, scroll_sel)
                await page.wait_for_timeout(800)
            except Exception:
                pass

        await show_step_banner(page, title, label, step)
        await page.wait_for_timeout(int(hold * 1000))
        await hide_step_banner(page)
        caption_times.append((label, hold))

    await context.close()

    webm = find_recorded_webm(work)
    if not webm:
        raise RuntimeError(f"No webm recorded for {stem} in {work}")

    mp4_out = OUT_DIR / f"{stem}.mp4"
    webm_to_mp4(webm, mp4_out)
    write_step_captions(chapter, caption_times)

    for f in work.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        work.rmdir()
    except OSError:
        pass

    return mp4_out, session_logged_in


async def main_async(
    chapter_filter: list[int] | None,
    *,
    with_narration: bool,
    narration_only: bool,
) -> int:
    chapters = load_chapters()
    stems = [c["stem"] for c in chapters]
    all_durations = load_step_durations()

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
            logged_in = False

            for i in indices:
                ch = chapters[i]
                stem = ch["stem"]
                step_durs = all_durations.get(stem)
                log(f"Recording {stem} ({len(ch.get('recording_steps', []))} steps)...")
                mp4_path, logged_in = await record_chapter_video(
                    browser,
                    base,
                    ch,
                    ctx,
                    username=username,
                    password=password,
                    logged_in=logged_in,
                    step_audio_durations=step_durs,
                )
                if with_narration:
                    mux_narration(mp4_path, stem)
                size_kb = mp4_path.stat().st_size // 1024
                log(f"  -> {mp4_path.name} ({size_kb} KB)")

            await browser.close()
    finally:
        if pw_backup is not None:
            log("Restoring original password...")
            restore_password(uid, pw_backup)

    total = sum(p.stat().st_size for p in OUT_DIR.glob("ch*.mp4"))
    log(f"Done. Videos in {OUT_DIR} (total ~{total // 1024} KB)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", help="Comma-separated chapter numbers 1-10")
    parser.add_argument("--with-narration", action="store_true", help="Mux TTS audio")
    parser.add_argument("--no-narration", action="store_true", help="Silent videos")
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
