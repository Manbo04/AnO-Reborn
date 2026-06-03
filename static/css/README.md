# Game UI CSS

| File | Purpose |
|------|---------|
| `tokens.css` | Design tokens (--game-space-*, radii, HUD heights) |
| `game-shell.css` | Resource HUD, mobile shell, bottom nav |
| `game-experience.css` | Province base view, district map, build sheet |
| `game-country.css` | Country hub cards |
| `game-war.css` | War unit cards |

Run `python3 scripts/bundle_game_css.py` after editing any file above (appends into `static/style.css`).

`province-base.css` is deprecated — rules live in `game-experience.css`.
