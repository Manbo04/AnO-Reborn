# Province UI redesign: plan and as-built notes

## Corrections to the original plan (found while building)
- **The live page is `province_v2.html`**, not `province.html` (Railway `THEME_V2_PAGES` includes `province`/`provinces`). The redesign changes the v2 templates. The classic `province.html` is now the rollback path (set `THEME_V2_PAGES` without `province`), so it was **not deleted**. Approved item "delete the unused templates" was therefore not done.
- **Tabs as built:** Overview, Buildings (electricity, retail, public works + Quick Build), Military (Iron Dome + military buildings), Resources (raw resources, other-biome reference, processing). The planned "Economy" and "Land" tabs were merged because the game's real split is city slots vs land slots. Buy Cities / Buy Land stay together in Overview (they share one form and one cost script).
- **Toasts:** buy/sell success toasts already existed (flash messages); nothing new was needed. Failures still render the existing full-page error (unchanged server behaviour).
- **Repeated Lumber Mills / Pumpjacks / Mines sections are NOT a copy-paste bug.** They are terrain branches (`if province.location in [...] / elif`), so each province shows one of them. The terrain table was extracted into the catalog and a test checks it equals `app_core/economy/biome_buildings.py` for all 7 biomes.
- **"Aerodromes: Aerodromes" label:** not reproducible on master any more; the live label was "Aerodromes: Aerodomes cost $22M..." (typo from the unit key). Fixed: it now reads "Air Bases" like the rest of the game.
- **Cache concern (B2) resolved:** buy/sell/upload invalidate the cache and redirect with a cache-busting `?_=` parameter, verified in the browser.

## Original audit and plan (as approved)

Base: origin/master 92e0f209d. Branch: `province-ui-redesign`. Test account: id 16 (2 provinces). BEFORE shots: `docs/province-ui/before/`.

## 1. Audit

### Files
| Area | Files |
|---|---|
| Routes | `province.py`: `/provinces`, `/province/<id>`, `/province/<id>/{rename,delete,set-capital,flag,image,iron_dome}`, `/createprovince`, `/api/province/<id>/{layout,slot/<slot>,quick_build}`, `/build_structure`, `/<way>/<units>/<id>` (generic buy/sell), `/mass_purchase/{preview,buy,sell}`, `/calculator` |
| Templates (live) | `province.html` (2,722 lines), `provinces.html`, `createprovince.html`, partials `province_{status,settings,info,base_view,base_slots}.html`, `distribution_alert.html` |
| Templates (not live) | `province_v2.html` (2,781), `provinces_v2.html`, `createprovince_v2.html`. Only served if the Railway env `THEME_V2_PAGES` lists them. Live HTML confirms the classic ones are served. |
| JS | `province-base.js` (map/district sheet, quick build), `province-demographics.js` (Chart.js), `province-zones.js` |
| CSS | `css/game-province.css` (679 lines), `css/province-base.css`, plus a large inline `<style>`/`<script>` in `province.html` |
| Service/Data | `services/province_service.py`, `repositories/province_repository.py`, `app_core/economy/province_{effects,energy,power}.py` |
| Tests | 13 province test files (`tests/test_province_*.py`, `test_provinces*.py`, `test_integration_province.py`) |

### What a player sees on `/province/<id>` (top to bottom, desktop)
1. Title banner (name, flag, optional custom image)
2. Distribution alert (a red box of 3 paragraphs; the same fact repeats in the rations card below)
3. District map "Base view" (feature-flagged; a second, separate UI for building) + a nudge to switch to it
4. 3 status cards: Powered / Rations / Consumer goods
5. "Edit" button, which expands settings: picture, flag, capital, rename, delete
6. Province information: population, happiness, productivity, consumer spending, pollution, city slots, land slots, electricity (each row ~100px tall)
7. Demographic radar chart, population breakdown, education breakdown, education capacity
8. "What changes each hour": happiness, pollution, productivity (tap to expand)
9. Iron Dome card (build/dismantle)
10. Quick Build (dropdown of every building + quantity + Build)
11. Purchase Cities / Purchase Land (cost preview + buy)
12. Infrastructure: 40-chip "Jump to" strip, then City/Land tabs, then sub-tabs (Electricity / Retail / Public Works ...)
13. About 40 hand-copied blocks "You have N <building>" with Buy / Sell, quantity box and cost text, e.g. Coal/Oil/Solar/Wind/Geothermal/Hydro/Nuclear, Food Bank, Gas Station, General Store, Farmers Market, Bank, Mall, Distribution Center, Industrial District, Workshop, Jewelry, Automotive, Parks, Libraries, Hospitals, schools, Universities, Monorail/Railway/Metro, Army/Air/Naval bases, Admin, Silos, Drone Sites, Missile Batteries, Farms, Fisheries, all mines, Pumpjacks, Lumber, factories, refineries

### Measured BEFORE (live, account 16, province 252)
| | Desktop 1280 | Mobile 390 |
|---|---|---|
| Page height | 6,188 px | 8,885 px |
| Buttons | 151 | 144 |
| DOM nodes | 2,467 | 2,411 |
| `<h1>` / `<h2>` / `<h3>` | 2 / 52 / 77 | same |
| Inputs with no label | 51 | 51 |
| Horizontal overflow | none | none |
| HTML size / load | 285 KB / 1.3 s | |
No console errors. `/provinces`: 836 nodes, 26 buttons, fine.

### Problems
1. **Same thing done 40 times.** Every building is its own copy-pasted block with its own headings. This is the root of the "all over the place" feeling and of 2,700 lines of template.
2. **Three ways to build** (Quick Build dropdown, map district sheet, per-building blocks) plus two ways to view (Base view vs Classic), with no clear primary.
3. **No hierarchy at top.** The player must scroll past 3 alert boxes, a settings button, a 100px-per-row stats list and 4 tables to reach any action. Key vitals (population, happiness, power, food) are not on one line.
4. **Mixed card styles** (`infodiv`, `stat-card`, `province-status-card`, plain tables, a left-aligned header bar and centred h3 headers mixed together).
5. **Numbers are raw** (`34,994,538`, `107,750,196 (100.0%)`) and the same shortfall is stated in 2 places.
6. **Mobile:** 8,885 px of scroll; the Jump-to strip is a 40-chip row; in-page tabs inside a table; flex-badge tab labels truncate.
7. **Accessibility:** 51 unlabeled inputs, two `<h1>`, 129 headings with no real outline, tabs not keyboard-operable.
8. **Feedback:** build/buy is a full-page POST + reload; the Base view has a toast but the classic view does not.
9. **Dev wording** ("Quick Build (Normalized)").
10. **Performance:** route runs 13 queries in one connection, with loops done in Python, so **no per-row N+1 found**. The cost is the 285 KB, 2,400-node page, and `@cache_response(30s)` on the page (see bug list).

### Bugs seen, NOT to be fixed in the redesign (reported separately)
- B1: Quick Build "Aerodromes" option text reads "Aerodromes — Aerodromes" (documented in the UI skill; to re-verify live).
- B2: Province page is cached 30 s (`@cache_response`). Need to confirm the cache is cleared after a build/buy, otherwise numbers look stale after an action.
- B3: Section list repeats "Lumber Mills" 3x, "Pumpjacks" 2x, "Coal Mines"/"Bauxite Mines" 2x. May be intentional (different tabs), to check; if copy-paste, buy/sell may point at the same unit.
- B4: `province_v2.html`/`provinces_v2.html` are ~2,800 lines of dead code unless `THEME_V2_PAGES` is set. Will ask before deleting.

## 2. Plan

### Principles
Only existing data and actions. No change to routes, form actions (`/buy/<unit>/<id>`, `/sell/...`, `/build_structure`, rename/delete/etc.), game rules or costs. Keep AnO look: tokens (`--accent`, `--foreground`...), Roboto, Material Icons, `stat-card`, `game_button`, `game_panel` macros. Mobile first (390 px).

### Information architecture
Header (always visible): flag + name + Capital badge + **Edit** (settings sheet).
Vitals strip (stat cards, one row desktop, 2x2 mobile): Population (growth/h) · Happiness · Productivity · Power (12/3) · Rations · Consumer goods. Red/green state and one-line reason; tap opens details. This replaces the 3 alert boxes + 3 status cards + the first stats list.

Tabs (URL hash `#overview` etc., works with no JS as stacked sections):
1. **Overview**: vitals detail, slots (city/land used/total, with Buy Cities / Buy Land inline), pollution/consumer spending, hourly changes, demographics (radar, population, education) collapsed under "Demographics".
2. **Buildings**: one searchable, grouped list/table (see below). Quick Build and the district map live here as "Build" (map stays as an alternate view toggle, unchanged logic).
3. **Military**: Iron Dome + army/air/naval bases, admin, silos, drone sites, missile batteries (same rows component, filtered).
4. **Economy**: energy balance (production/consumption tables), coal/oil/etc. plants, retail/distribution, resources buildings with industry bonuses.
5. **Land**: Buy Land, farms/fisheries/mines/lumber/pumpjacks etc.
(Which building falls in which tab follows the groups already in the game's `INFRA_TYPE_BUILDINGS`. No new categories.)
Settings (picture, flag, capital, rename, delete) move to an **Edit** side sheet. Delete stays in a clearly separate "Danger zone" with the existing type-the-name confirmation.

### Wireframes
Desktop (1280):
```
[flag] Province 1  (Capital)                             [Edit] [Base view]
+-----------+-----------+-----------+-----------+-----------+-----------+
| Pop 35.0M | Happy 0%  | Prod 100% | Power OK  | Rations   | Goods     |
| -91K/h    |           |           | 12 / 3    | 23% fed   | 0% met    |
+-----------+-----------+-----------+-----------+-----------+-----------+
 Overview | Buildings | Military | Economy | Land
+--------------------------------------------+--------------------------+
| Slots   City 5/10K [Buy cities]            | Demographics (collapsed) |
|         Land 20/10K [Buy land]             | Education      (collapsed)|
| Hourly: Happiness -2/h  Pollution +53/h    |                          |
+--------------------------------------------+--------------------------+
```
Buildings tab:
```
[ Search buildings...      ] [All|Energy|Retail|Public|Resources|Industry]
Group: Energy                                          (3 of 7 built)
 Building           Owned  Cost each          Qty     Actions
 Coal Power Plant     2    $X + 6t steel...   [ 1 ]   [Build] [Dismantle]
 ...
```
Mobile (390): vitals 2x2 grid then a scrollable tab bar (fade edge); building rows become cards:
```
+--------------------------------+
| Coal Power Plant         x2    |
| $250K, 6t steel  (tap: details)|
| [ - 1 + ]  [Build] [Dismantle] |
+--------------------------------+
```
Province list (`/provinces`): keep, but add compact table as default on mobile, sortable columns (name, population, growth, happiness, tax) via client-side sort, existing `?q=` search and pager unchanged.

### Components (new, reusable, tokens only)
- `macros/province_ui.html`: `vital_card`, `building_row` (ONE macro replaces ~40 blocks; same form posts), `slot_meter`, `empty_state`.
- Toast on every action (reuse the Base-view toast); classic POST → redirect → flash message shown as a toast. Server behaviour unchanged.
- Primary button = Build/Buy (accent), secondary = Dismantle/Sell (outline), danger = Delete.
- Numbers: new `compact` Jinja filter (1.2M, 45.5K), full value in `title`/tooltip. Used on cards and lists; exact numbers stay where a player needs precision (costs, inputs).
- Icons: only the Material icons the game already uses.
- A11y: one `<h1>`, `<h2>` per tab section, labels/`aria-label` on all inputs, real tab roles + arrow keys, focus rings.

### Commits (one section at a time, each shippable)
1. Macros + `compact` filter + tests (no visible change)
2. Header + vitals strip, merges alerts/status cards
3. Tabs shell (hash routing, no-JS fallback)
4. Overview tab (slots, hourly, demographics collapsed)
5. Buildings via `building_row` (replace the ~40 blocks, verify each unit's form action byte-identical)
6. Military + Economy + Land tab grouping
7. Edit sheet (settings) + toasts
8. `/provinces` sortable compact table
9. A11y + CSS cleanup

### Risks
- Biggest: replacing 40 blocks could change a form action or unit. Mitigation: a test that renders old vs new template and compares the set of (action, unit, province id) tuples.
- Other pages/JS link to ids on this page (`province-base.js`, `province-zones.js`, tutorial). Mitigation: keep existing element ids/data attributes.
- 30 s page cache (B2) can make verification look wrong; will check invalidation first.
- Shared checkout is dirty and 122 commits behind, so all work is in a separate worktree off fresh master.
- `/province/<id>` is also viewed by other players (visitor mode) and crawlers: keep that rendering working (tests + visual check).

### Verification
Existing test suite + new render tests; click through every action on account 16 in real Chrome at 1280 and 390 (build, dismantle, buy/sell each unit group, buy city/land, rename, flag/image, capital, iron dome; delete only on a throwaway-free path, i.e. verified by render + route test, not by deleting a real province); AFTER shots; console/overflow/N+1 (query count before vs after); the 6-point door test in the PR.

### Questions for you (my recommendation in bold)
1. Keep the district map "Base view" as is, as an alternate view on the Buildings tab? **Yes**
2. OK to delete the unused `*_v2` templates in a final separate commit? **Yes, but later**
3. Include the Base-view nudge banner? **Drop it, the toggle is in the header**
