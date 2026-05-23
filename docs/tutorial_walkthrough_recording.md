# Tutorial walkthrough screen recording

Nation Academy chapter videos (`static/tutorial/videos/ch01-*.mp4` … `ch10-*.mp4`) are regenerated as **in-game Playwright screen video** with smooth cursor motion, tab chips in the step banner, and optional per-step TTS.

## Prerequisites

- Python 3.10+
- `ffmpeg` on PATH
- Network access to production site and Railway Postgres (public proxy)

```bash
pip install playwright psycopg2-binary bcrypt python-dotenv requests edge-tts
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

## Run (full pipeline)

From repo root:

```bash
export DATABASE_PUBLIC_URL='postgresql://...'   # Railway public URL
python3 scripts/generate_tutorial_narration.py
python3 scripts/record_tutorial_walkthroughs.py --with-narration
```

Single chapters:

```bash
python3 scripts/generate_tutorial_narration.py   # all chapters (or split manually)
python3 scripts/record_tutorial_walkthroughs.py --chapters 2,7 --with-narration
```

Silent capture (no audio mux):

```bash
python3 scripts/record_tutorial_walkthroughs.py --no-narration
```

Output:

- `static/tutorial/videos/*.mp4` — scaled H.264 (960×540)
- `static/tutorial/audio/{stem}.mp3` — concatenated per-step narration
- `static/tutorial/captions/{stem}.vtt` — step-aligned captions
- `static/tutorial/step_durations.json` — hold times synced to audio (used by recorder)

Commit assets and bump `?v=` on tutorial video/CSS/JS after replace. Deploy `master` for Railway.

## Chapter metadata

Each `recording_steps[]` entry in [`static/tutorial/chapters.json`](../static/tutorial/chapters.json) supports:

| Field | Purpose |
|-------|---------|
| `label` | Step title (banner + captions + stepper UI) |
| `path` | Route (`{province_id}` placeholders resolved from test user) |
| `tab` | In-game tab id (e.g. `countryrevenue`) — clicked with smooth mouse motion |
| `tab_label` | Short label for tutorial stepper pill |
| `tab_group` | Chip row in banner (`country`, `province`, `province.land`, `military`, `upgrades`, `none`) |
| `narration` | Per-step TTS script |
| `hold_sec` | Minimum seconds on screen (extended if audio is longer) |
| `scroll` | Optional selector for smooth scroll before hold |
| `action` | `login` for chapter 1 sign-in step |

Tab label map: [`scripts/tutorial_chapter_meta.py`](../scripts/tutorial_chapter_meta.py) (mirrors `static/script.js` `TAB_GROUPS`).

## Recording behavior (v3)

- One **Playwright `record_video`** per chapter (1280×720), converted with ffmpeg (CRF 26).
- **Smooth cursor**: stepped `mouse.move` + visible overlay dot; smooth clicks on tabs and login fields.
- **Step banner**: chapter title, step label, and **tab chips** when `tab_group` is set.
- **Hold duration**: `max(hold_sec, audio_duration + 0.8)` when `step_durations.json` exists.

## Safety rules

The recorder is **read-only** in the browser:

- Only navigates with GET (except `/login/` POST for chapter 1)
- Blocks POSTs to war, market offers, account deletion, coalition bank, etc.
- Restores the test user’s original password hash after the run

## Size guardrail

Aim for **&lt; 40 MB** total across 10 files. Increase `VIDEO_CRF` in `record_tutorial_walkthroughs.py` if needed.

## Slideshow fallback

Offline / no DB:

```bash
python3 scripts/generate_tutorial_videos.py
```

## CI auto re-record

[`.github/workflows/tutorial-videos.yml`](../.github/workflows/tutorial-videos.yml) runs narration generation, then recording with `--with-narration`, and opens a PR with videos/audio/captions.

Required GitHub secret: `DATABASE_PUBLIC_URL`. Optional: `TUTORIAL_RECORD_TMP_PASSWORD`, repo variable `TUTORIAL_RECORD_BASE_URL`.

## Verification checklist

1. Cursor moves smoothly to tabs (no instant jumps between steps on the same page).
2. Active in-game tab matches the step (Revenue, Land, Industry, etc.).
3. Banner shows tab chip row with the active tab highlighted.
4. `/tutorial` step strip under the video tracks playback; clicking a step seeks the video.
5. Narration is audible, not rushed; test user password restored after run.
