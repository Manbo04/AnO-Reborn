# Stylesheet layout

| File | Role |
|------|------|
| `tokens.css` | Game UI design tokens (spacing, radii, HUD heights) |
| `game-shell.css` | Mobile bottom nav, resource HUD, cards |
| `province-base.css` | Phaser canvas container |
| `game-war.css` | War / unit selection mobile polish |
| `game-country.css` | Country home hub (mobile) |
| `../style.css` | Legacy monolith (navbar, tables, province tabs) |

New game UI should go in dedicated files above; avoid growing `style.css` further.
