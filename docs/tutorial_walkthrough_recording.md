# Tutorial walkthrough screen recording

Nation Academy chapter videos (`static/tutorial/videos/ch01-*.mp4` … `ch10-*.mp4`) can be regenerated as **real in-game screen captures** using Playwright.

## Prerequisites

- Python 3.10+
- `ffmpeg` on PATH
- Network access to production site and Railway Postgres (public proxy)

```bash
pip install playwright psycopg2-binary bcrypt python-dotenv requests
playwright install chromium
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_PUBLIC_URL` | (see script fallback) | Resolve province/coalition IDs; temporary password swap for test user |
| `TUTORIAL_RECORD_BASE_URL` | `https://affairsandorder.com` | Site to record |
| `TUTORIAL_RECORD_USER_ID` | `16` | Tester of the Game |
| `TUTORIAL_RECORD_TMP_PASSWORD` | `tutorial-record-2026` | Temporary password during run (restored after) |
| `TUTORIAL_RECORD_SKIP_DB` | unset | Set to `1` to skip DB password swap (supply `TUTORIAL_RECORD_USERNAME` + `TUTORIAL_RECORD_PASSWORD`) |

## Run (all chapters)

From repo root:

```bash
export DATABASE_PUBLIC_URL='postgresql://...'   # Railway public URL
python3 scripts/record_tutorial_walkthroughs.py
```

Single chapters:

```bash
python3 scripts/record_tutorial_walkthroughs.py --chapters 2,7
```

Output overwrites `static/tutorial/videos/*.mp4`. Commit and deploy to `master` for Railway.

## Safety rules

The recorder is **read-only** in the browser:

- Only navigates with GET (except `/login/` POST for chapter 1)
- Blocks POSTs to war, market offers, account deletion, coalition bank, etc.
- Restores the test user’s original password hash after the run

Do not click buy/sell/declare buttons during manual OBS recordings either.

## Manual OBS fallback

If automation is unavailable:

1. Log in as **Tester of the Game** on production.
2. Record 45–75s per chapter at **1280×720**, following the table in `scripts/record_tutorial_walkthroughs.py` (`build_flows`).
3. Export H.264 MP4, scale to **960×540** if needed:

   ```bash
   ffmpeg -i raw.mp4 -vf "scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2" -c:v libx264 -pix_fmt yuv420p -crf 28 -an static/tutorial/videos/ch02-provinces.mp4
   ```

4. Keep filenames: `ch01-welcome.mp4` … `ch10-coalitions.mp4`.
5. Bump `?v=` on video sources in `templates/tutorial.html` after replace.

## Size guardrail

Aim for **&lt; 25 MB** total across 10 files. Increase CRF (e.g. 30) in the script’s `ffmpeg_to_mp4` if needed.

## Slideshow fallback

Offline / no DB:

```bash
python3 scripts/generate_tutorial_videos.py
```
