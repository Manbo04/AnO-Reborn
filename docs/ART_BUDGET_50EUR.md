# €50 Art Budget — Recommended Purchases

Goal: maximum visual upgrade for **mobile HUD + province base + a few hero buildings**, not full 38-building catalog.

## Recommended stack (≈ €45–50 total)

### 1. UI kit (~€15–20)

Search itch.io / Unity Asset Store / Craftpix for:

- **"Mobile game UI kit"** or **"strategy game GUI"**
- Must include: panel frames, buttons, progress bars, resource bar background
- License: commercial OK for web game

**After purchase:** export PNGs to `static/images/game/ui/` and wire in `game-shell.css` as backgrounds.

### 2. Icon pack (~€10–15)

- **16–32 resource icons** (gold, food, wood, stone style) OR fantasy reskin
- Rename to match `RESOURCE_LEGACY_IMAGES` keys in `game_ui.py`
- Place in `static/images/game/resources/`

### 3. Building / unit slice (~€15–20)

Pick **one** pack with isometric or 3/4 buildings:

- Priority buildings for base view: `farms`, `coal_burners`, `iron_mines`, `army_bases`, `steel_mills`
- Priority units: `soldier`, `tank`, `fighterjet` equivalents

Place in `static/images/game/buildings/` and `static/images/game/units/` using manifest paths.

## Free supplements

- **Kenney.nl** — CC0 UI and icons (fill gaps)
- **Google Fonts** — already using Roboto
- **AI batch** — only for backgrounds; keep one locked style prompt

## What NOT to buy on €50

- Full animated battle packs
- World map tilesets (deferred — see countries stub)
- 30+ unique building meshes

## Integration checklist

1. Buy assets → drop files per paths in `asset-manifest.json`
2. Run `python3 scripts/generate_asset_manifest.py` if keys added
3. Optional: `python3 scripts/convert_images_webp.py` for bandwidth
4. Hard refresh on phone; verify province base canvas loads new sprites

## Env rollback

```bash
FEATURE_GAME_SHELL=false
FEATURE_PROVINCE_BASE_VIEW=false
```

Redeploy without removing files.
