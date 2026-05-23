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
5. Push to `master` (Railway auto-deploys)
6. Verify production:

```bash
curl -s "https://affairsandorder.com/" | grep -o 'style.css[^"]*'
curl -s "https://affairsandorder.com/static/style.css?v=N" | wc -c
curl -s "https://affairsandorder.com/static/province-base.js?v=N" | grep -c quickBuild
```

Expect bundled CSS ~120KB+ with `province-map-node` rules. JS must include `quickBuild` (not Phaser).

## Nixpacks

Build phase runs `python3 scripts/bundle_game_css.py` — see `nixpacks.toml`.

## Cloudflare / browser cache

Static assets use long `immutable` cache. Always bump `?v=` when changing CSS/JS.

## Test account

Use user **16** only. Clean up offers/builds after API tests.
