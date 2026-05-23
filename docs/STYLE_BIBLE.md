# Affairs and Order — Game Visual Style Bible

**Path:** Hybrid mobile strategy (Lords Mobile / Clash of Clans feel)  
**Platform:** Mobile web first (PWA)  
**Perspective:** Top-down / slight isometric for province base slots (Phaser canvas)

## Palette (matches CSS tokens)

| Role | Light | Dark |
|------|-------|------|
| Background | `#eef1f5` | `#13171e` |
| Panel | `#ffffff` | `#1c2029` |
| Accent | `#00a7e1` | `#00a7e1` |
| Gold / premium | `#d4a843` | `#d4a843` |
| Success | `#2d9f6f` | `#2d9f6f` |
| Danger | `#d35649` | `#d35649` |

## Typography

- **UI:** Roboto (existing)
- **Sizes:** Body 16px minimum on mobile; HUD chips 14px+; nav labels 10–11px

## Iconography

1. **HUD resources:** 64×64 PNG with transparent padding → `static/images/game/resources/{key}.png`
2. **Buildings:** 256×256 master, downscaled in canvas → `static/images/game/buildings/{building_key}.png`
3. **Units:** 256×256 idle pose → `static/images/game/units/{unit_key}.png`
4. **Biomes:** 1024×768 landscape → `static/images/game/biomes/{biome}.jpg`

Until game/ assets exist, manifest falls back to legacy `static/images/*.jpg`.

## UI chrome

- Panel radius: 12–16px (`--game-radius-md/lg`)
- Bottom nav height: 64px + safe area
- Touch targets: minimum 44×44px

## Navigation (v1)

- **Top navbar** + **home quick-link grid** (`quick_nav.html`) + **resource HUD** on mobile
- Bottom tab bar was removed (PR #41); do not re-add without product sign-off

## Non-goals (v1)

- Full world territory map
- Battle animations
- 3D / Unity client

## File naming

Use normalized DB keys: `coal_burners`, `fighter_jets`, `consumer_goods` — see `static/asset-manifest.json`.
