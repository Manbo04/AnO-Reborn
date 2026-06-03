# Game UI — Deploy and rollback

## Feature flags (Railway env)

| Variable | Default | Effect |
|----------|---------|--------|
| `FEATURE_GAME_SHELL` | `true` | Resource HUD, quick links, mobile cards |
| `FEATURE_PROVINCE_BASE_VIEW` | `true` | Province map command center |
| `FEATURE_GAME_PWA` | `true` | Web manifest + service worker |

Set to `false` to roll back without redeploying code.

## Every visual release

1. `python3 scripts/generate_asset_manifest.py`
2. `python3 scripts/bundle_game_css.py`
3. Commit `static/style.css` and `static/asset-manifest.json`
4. Bump cache query strings in `templates/layout.html` and `templates/province.html`:
   - `style.css?v=N`
   - `province-base.js?v=N`
   - `game-shell.js?v=N`
5. Regenerate vivid inventory baseline:
   - `python3 scripts/generate_visual_asset_inventory.py`
6. Push to `master` (Railway auto-deploys if linked)
7. Verify production:

```bash
curl -s "https://affairsandorder.com/" | grep -o 'style.css[^"]*'
curl -s "https://affairsandorder.com/static/style.css?v=N" | wc -c
curl -s "https://affairsandorder.com/static/province-base.js?v=N" | grep -c quickBuild
```

Expect bundled CSS with `province-map-node` rules and atmosphere markers (`toppershimmer`, `province-node-glint`).

## Visual batch QA gate (screenshots + marker checks)

### Local/manual

```bash
python3 scripts/capture_visual_snapshots.py
python3 scripts/verify_visual_batch_live.py
```

Screenshot output defaults to `artifacts/visual-snapshots/`.

### GitHub Actions

- Workflow: `.github/workflows/visual-screenshot-qa.yml`
- Triggers on visual file changes and supports manual dispatch.
- Uploads screenshot artifacts and runs live marker checks against deploy URL.

## Nixpacks

Build phase runs `python3 scripts/bundle_game_css.py` — see `nixpacks.toml`.

## Cloudflare / browser cache

Static assets should use finite cache with revalidation on new web code. Always bump `?v=` for CSS/JS/image URL changes to avoid stale browser cache.

## Test account

Use user **16** only. Clean up offers/builds after API tests.
