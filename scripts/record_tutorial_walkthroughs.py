#!/usr/bin/env python3
"""
Record Nation Academy chapter videos as real in-game screen captures.

Requirements:
  pip install playwright psycopg2-binary bcrypt python-dotenv requests
  playwright install chromium
  ffmpeg on PATH

Environment:
  DATABASE_PUBLIC_URL or DATABASE_URL — production DB (for ids + temp login password)
  TUTORIAL_RECORD_BASE_URL — default https://affairsandorder.com
  TUTORIAL_RECORD_USER_ID — default 16 (Tester of the Game)
  TUTORIAL_RECORD_TMP_PASSWORD — temp password while recording (restored after)
  TUTORIAL_RECORD_SKIP_DB — if "1", use env username/password only (no DB password swap)

Run from repo root:
  python3 scripts/record_tutorial_walkthroughs.py
  python3 scripts/record_tutorial_walkthroughs.py --chapters 1,2
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "tutorial" / "videos"
TMP_DIR = OUT_DIR / "_record_tmp"

VIDEO_W = 1280
VIDEO_H = 720
OUT_W = 960
OUT_H = 540
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

CHAPTER_OUTPUTS = [
    "ch01-welcome",
    "ch02-provinces",
    "ch03-resources",
    "ch04-economy",
    "ch05-population",
    "ch06-military",
    "ch07-market",
    "ch08-upgrades",
    "ch09-war",
    "ch10-coalitions",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


def get_db_url() -> str:
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if url:
        return url
    # Dev fallback (public Railway proxy in repo scripts)
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


def ffmpeg_to_mp4(webm: Path, mp4: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(webm),
        "-vf",
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "28",
        "-movflags",
        "+faststart",
        "-an",
        str(mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


async def slow_scroll(page, steps: int = 8, pause_ms: int = 450) -> None:
    for _ in range(steps):
        await page.evaluate(
            "window.scrollBy(0, Math.max(200, window.innerHeight * 0.35))"
        )
        await page.wait_for_timeout(pause_ms)


def guard_request(method: str, url: str) -> None:
    if method.upper() == "GET":
        return
    low = url.lower()
    if "/login" in low:
        return
    if any(f in low for f in BLOCKED_POST_FRAGMENTS):
        raise RuntimeError(f"Blocked non-GET during capture: {method} {url}")


async def browser_login(page, base: str, username: str, password: str) -> None:
    """Log in through the browser (production blocks bare POST /login/ with 403)."""
    await page.goto(f"{base.rstrip('/')}/login", wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(800)
    await page.fill('input[name="username"]', username)
    await page.fill('input[name="password"]', password)
    await page.evaluate("document.getElementById('login-form').submit()")
    await page.wait_for_load_state("networkidle", timeout=60000)
    await page.wait_for_timeout(1000)


async def record_chapter(
    playwright,
    base: str,
    stem: str,
    steps_fn,
    *,
    username: str,
    password: str,
    include_login: bool,
) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    webm_path = TMP_DIR / f"{stem}.webm"
    mp4_path = OUT_DIR / f"{stem}.mp4"

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        record_video_dir=str(TMP_DIR),
        record_video_size={"width": VIDEO_W, "height": VIDEO_H},
        viewport={"width": VIDEO_W, "height": VIDEO_H},
        locale="en-US",
    )
    context.on("request", lambda req: guard_request(req.method, req.url))
    page = await context.new_page()

    try:
        if not include_login:
            await browser_login(page, base, username, password)
        await steps_fn(page, base, username, password)
    finally:
        await context.close()
        await browser.close()

    # Playwright names files arbitrarily in record dir — pick newest webm
    webms = sorted(TMP_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not webms:
        raise FileNotFoundError(f"No webm produced for {stem}")
    latest = webms[0]
    if latest != webm_path:
        latest.rename(webm_path)

    ffmpeg_to_mp4(webm_path, mp4_path)
    webm_path.unlink(missing_ok=True)
    size_kb = mp4_path.stat().st_size // 1024
    log(f"  -> {mp4_path.name} ({size_kb} KB)")
    return mp4_path


def build_flows(ctx: dict[str, Any], uid: int):
    pid = ctx.get("province_id")
    col = ctx.get("coalition_id")

    async def ch01(page, base: str, username: str, password: str) -> None:
        await browser_login(page, base, username, password)
        await page.goto(f"{base}/country", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await slow_scroll(page, 6, 500)
        await page.goto(f"{base}/mechanics", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 4, 500)

    async def ch02(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/provinces", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 3, 450)
        if pid:
            await page.goto(f"{base}/province/{pid}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)
            await slow_scroll(page, 10, 500)

    async def ch03(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/country/id={uid}", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 7, 500)
        if pid:
            await page.goto(f"{base}/province/{pid}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(1500)
            await slow_scroll(page, 8, 450)

    async def ch04(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/country", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await slow_scroll(page, 10, 500)
        await page.goto(f"{base}/mechanics/revenue", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 5, 450)

    async def ch05(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/country", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await slow_scroll(page, 6, 500)
        await page.goto(f"{base}/mechanics/rations", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        await slow_scroll(page, 4, 450)

    async def ch06(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/military", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 12, 500)

    async def ch07(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/market", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        await slow_scroll(page, 5, 450)
        await page.goto(f"{base}/statistics", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 6, 500)

    async def ch08(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/upgrades", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 12, 500)

    async def ch09(page, base: str, username: str, password: str) -> None:
        await page.goto(f"{base}/wars", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        await slow_scroll(page, 5, 450)
        await page.goto(f"{base}/mechanics/war", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await slow_scroll(page, 5, 450)

    async def ch10(page, base: str, username: str, password: str) -> None:
        if col:
            await page.goto(
                f"{base}/coalition/{col}",
                wait_until="networkidle",
                timeout=60000,
            )
        else:
            await page.goto(f"{base}/coalitions", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        await slow_scroll(page, 8, 500)

    return [
        ("ch01-welcome", ch01, True),
        ("ch02-provinces", ch02, False),
        ("ch03-resources", ch03, False),
        ("ch04-economy", ch04, False),
        ("ch05-population", ch05, False),
        ("ch06-military", ch06, False),
        ("ch07-market", ch07, False),
        ("ch08-upgrades", ch08, False),
        ("ch09-war", ch09, False),
        ("ch10-coalitions", ch10, False),
    ]


async def main_async(chapter_filter: list[int] | None) -> int:
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
        log(f"Recording as: {username!r} (province={ctx['province_id']}, coalition={ctx['coalition_id']})")
        pw_backup = backup_and_set_password(uid, tmp_pw)
        password = tmp_pw
    else:
        if not username:
            log("TUTORIAL_RECORD_SKIP_DB=1 requires TUTORIAL_RECORD_USERNAME")
            return 1
        ctx = {"province_id": None, "coalition_id": None}

    flows = build_flows(ctx if not skip_db else fetch_context(uid), uid)
    indices = chapter_filter if chapter_filter else list(range(len(flows)))

    try:
        async with async_playwright() as p:
            for i in indices:
                stem, fn, include_login = flows[i]
                log(f"Recording {stem} ...")
                await record_chapter(
                    p,
                    base,
                    stem,
                    fn,
                    username=username,
                    password=password,
                    include_login=include_login,
                )
    finally:
        if pw_backup is not None:
            log("Restoring original password...")
            restore_password(uid, pw_backup)

    total = sum((OUT_DIR / f"{s}.mp4").stat().st_size for s in CHAPTER_OUTPUTS if (OUT_DIR / f"{s}.mp4").exists())
    log(f"Done. Videos in {OUT_DIR} (total ~{total // 1024} KB)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chapters",
        help="Comma-separated chapter numbers 1-10 (default: all)",
    )
    args = parser.parse_args()
    chapter_filter = None
    if args.chapters:
        chapter_filter = [int(x.strip()) - 1 for x in args.chapters.split(",")]

    import asyncio

    return asyncio.run(main_async(chapter_filter))


if __name__ == "__main__":
    raise SystemExit(main())
