# Game art overrides (hybrid UI)

Drop purchased or commissioned assets here. Paths must match `static/asset-manifest.json`.

```
game/
  ui/           # panels, buttons (optional)
  resources/    # resmoney.png style icons
  buildings/    # coal_burners.png etc.
  units/        # soldiers.png etc.
  biomes/       # grassland.jpg etc.
```

If a file is missing, templates fall back to legacy `static/images/*.jpg` via `onerror` and `game_ui.legacy_image_*`.

See `docs/ART_BUDGET_50EUR.md` for €50 budget shopping list.
