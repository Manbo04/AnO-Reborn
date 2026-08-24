---
name: ano-ui-design
description: Visual identity, design tokens, verification workflow, and known bug patterns for Affairs and Order (AnO-Reborn). Consult this before creating or modifying ANY template/CSS in this repo — mobile-first, keep faith with the existing look, don't redesign.
---

# Affairs and Order — UI Design Skill

This is Dede's living game, not a blank canvas. Every rule here came from a real bug report, a real correction, or a real research pass — not from general design taste. Read this before touching `templates/*.html` or `static/css/*.css`, and re-check the relevant section whenever a fix seems to require a new color, new component, or new pattern instead of reusing what's here.

## The one mandate that overrides everything else

**Mobile-first, and keep faith with the current look.** Most players are on phones/tablets. Every change is designed and checked at mobile width (~390px) FIRST, then scaled up — never the reverse. Reuse the token system and component classes below rather than inventing new colors, fonts, or component shapes on a per-page basis. If you think a fix needs a new visual pattern, it almost always doesn't — look harder for the existing class/token that already does the job, or propose fixing/extending the *shared* base rule so the improvement lands everywhere at once, not just on one page.

This used to say "not a redesign brief, don't take aesthetic risks" full-stop. **That changed 2026-08-19**: Dede explicitly asked for the UI to stop looking "all over the place" and read as "cool and neat like Uber or other mobile browser games" — a real visual-quality bar, not just bug fixes. The mandate now: incremental, but with real teeth — flatten decorative gloss (gradients → solid fills, done for `.templatedivbutton` and its variants), give shared components real *consistent* chrome instead of each page reinventing it slightly differently (done for `.stat-card`), tighten spacing/typography rhythm using the existing token scale. Still don't invent a new color palette or component language from scratch, and still verify every change live on mobile in both themes before calling it done — this is disciplined tightening-up, not a rebrand. The core brand accent (`#00a7e1`) and the token system stay; what's changing is how consistently and confidently they're applied.

## Visual identity (design tokens — use these, don't invent new ones)

Defined in `static/css/tokens.css` — the canonical source for color, spacing, and radius tokens (`.theme-light` / `.theme-dark` blocks, plus the shared `:root` scale below). The site supports both themes; always check a color choice against **both**, not just whichever theme you happen to be looking at.

**Light theme**
| Token | Value | Use |
|---|---|---|
| `--background` | `#eef1f5` | page background |
| `--foreground` | `#ffffff` | card/panel background |
| `--foregroundTwo..Eight` | `#f8f9fc` … `#e3e8f0` | layered surface shades, darkest last |
| `--border` | `#d0d7e2` | hairlines, card borders |
| `--tableOne` / `--tableTwo` | `#f4f6fa` / `#ffffff` | zebra-striped table rows |
| `--colorOne` | `#1a2332` | primary text |
| `--colorTwo` | `#ffffff` | text-on-accent |
| `--accent` | `#00a7e1` | the brand color — buttons, active tabs, links, focus rings |
| `--accent-hover` | `#0090c4` | |
| `--accent-subtle` | `#e6f6fc` | hover/selected background tint |
| `--gold` | `#d4a843` | currency/gold accents |
| `--success` / `--danger` | `#2d9f6f` / `#d35649` | revenue/expense, positive/negative |
| `--text-secondary` | `#5c6b7f` | captions, hints, secondary labels |

**Dark theme** (same variable names, swapped values) — `--background: #13171e`, `--foreground: #1c2029`, `--colorOne: #e0e4ea`, `--accent: #00a7e1` (constant across themes — this is *the* brand color), `--gold: #e0b84d`, `--success: #3ab87e`, `--danger: #e05a4d`. Full block: `static/css/tokens.css` `.theme-dark { ... }`.

**Spacing / radius / layout scale** (`:root` in `static/css/tokens.css`):
- Radius: `--game-radius-sm: 8px`, `-md: 12px`, `-lg: 16px`, `-xl: 24px`
- Space: `--game-space-xs: 4px`, `-sm: 8px`, `-md: 16px`, `-lg: 24px`, `-xl: 32px`
- Breakpoints in active use: `768px` (tablet), `720px`/`750px`/`800px`/`856px`/`1055px` (assorted component-specific — check for an existing `@media` block near the component you're editing before adding a new breakpoint)

**Typography:** `Roboto` (body/UI, loaded via Google Fonts), `Material Icons` / `Material Icons Outlined` (primary icon set — prefer these), Font Awesome 5 (`fas`/`far`/`fab` classes — secondary icon set, used in older templates and by third-party widgets like SimpleMDE).

**Established component classes** — reuse these, don't rebuild:
- `.templatedivflex2` / `.templatedivflex2left` / `.templatedivflex2right` — the standard two-column content layout
- `.templatetable` / `.templatetable2` / `.templatetable3` — data tables, already have mobile overflow + sticky-first-column rules at the `768px` breakpoint
- `.templatedivbutton` — standard button. **Flat fill as of 2026-08-19** (was a diagonal gradient) — solid `var(--accent)`/`var(--danger)`/`var(--success)`, sentence-case label (was uppercase + letter-spacing), soft neutral resting shadow (`0 1px 3px rgba(0,0,0,0.08)`), slightly stronger on hover. Part of the flat/minimal direction below — don't reintroduce gradients on new buttons.
- `.templateselect` / `.templatetextarea` / `.imageinput` — form controls
- `.stat-grid` / `.stat-card` / `.stat-label` / `.stat-value` — the resource/stat card grid used throughout country/province/military pages. **`.stat-card` gained real shared chrome as of 2026-08-19** (`static/style.css` ~line 5214): `background: var(--foreground)`, `border: 1px solid var(--border)`, `border-radius: var(--game-radius-md)`, `box-shadow: var(--shadow-card)`. Before this it had no visible chrome of its own — every page that used it (country/province/statistics) had silently reimplemented its own slightly-different background/border, which is exactly the kind of inconsistency that made the game feel "all over the place" rather than one coherent product. Page-specific `!important` overrides (e.g. `.country-demographics-panel .stat-card`, `body.page-provinces .stat-card`) still win where they exist — this is the fallback for everywhere else.
- `.radiodiv` / `.radioleft` / `.radioright` — the toggle-with-description list pattern (National Policies etc.) — note the touch-device fix below before reusing as-is
- `.game-panel-grid`, `.game-stack` — shared responsive panel utilities (`static/css/game-layout.css`)
- Edge-fade on horizontally-scrolling strips: `mask-image: linear-gradient(to right, black calc(100% - 28px), transparent 100%)` — established pattern (tab bars, resource HUD strip), reuse rather than a hard visual cutoff
- `.templatedivtitle` — the big colored page-title banner at the top of every content page (icon + page name, e.g. "🛡 Military"). **Refined 2026-08-19**: `background-color` now `var(--accent)` (was hardcoded `#00a7e1`), `border-radius` now `var(--game-radius-md)` (was a sharp `4px`, inconsistent with the rest of the 8-16px scale), shadow softened to a single `0 2px 12px rgba(0,0,0,0.15)` (was a heavy dual dark shadow). Same treatment on every page since it's a shared class — verified live on `/military` in both themes.
- `.templatecontentheaderleft` — section header bar (e.g. "Soldiers", "Country info"). `border-radius` now `var(--game-radius-sm)` (was `6px`) for the same consistency reason.

## Visual references

`references/` in this skill folder has real screenshots captured directly from a live local instance of this exact codebase (isolated throwaway account, never Dede's real data):
- `mobile-country-view.png` — Nation page at 390px: dark navbar, resource HUD chip strip, banner image with title overlay, tab bar (View/Revenue/News/Edit), `Country info` card with `stat-grid` rows
- `mobile-upgrades.png`, `mobile-military.png` — dense list/card pages at mobile width
- `desktop-country-view.png`, `desktop-upgrades.png` — same pages at 1440px, showing the desktop nav (`Internal Affairs` / `Global Affairs` / `Other` dropdown menus) that mobile replaces with the hamburger
- `public-signup.png` — unauthenticated page, dark hero image + light card pattern

These are a snapshot, not a spec — the live site is the real source of truth and changes over time. **Before any nontrivial visual work, take a fresh screenshot of the actual current page** (via the `mcp__claude-in-chrome__computer` browser tool at ~390×844, or by the isolated Playwright method below) rather than trusting these images to still be accurate.

**How these were captured, if you need fresh ones:** direct macOS `screencapture` of the interactive automation window is unsafe — it can capture Dede's real desktop instead if window focus is wrong (this happened once; the accidental capture was deleted immediately, nothing kept). Instead use headless Playwright (`playwright install chromium` if not already installed) against the local dev server on the disposable staging DB — see "Local dev + staging DB" below. Sign up a throwaway account, screenshot, then **delete the throwaway account from `ano_staging` immediately after** (see cleanup pattern in that section). Never point this at production, and never use it as a substitute for verifying real fixes on Dede's actual account (different purpose — see Verification workflow).

## Critical technical landmines

**1. The CSS bundle system — edit the right file or your change silently vanishes.**
`scripts/bundle_game_css.py` appends everything in `static/css/*.css` onto the end of `static/style.css`, after a marker comment (`/* === GAME UI BUNDLE (auto-generated) === */`, currently ~line 5569). Anything in `static/style.css` **after** that marker is auto-generated and gets overwritten on the next bundle run. Before editing `static/style.css`, check which side of the marker your target line is on:
- Before the marker → hand-written, edit directly.
- After the marker → find the real source in `static/css/<file>.css` and edit that instead.

**2. Hover-only content is invisible on touch, not just "hidden until interaction."**
Any `opacity: 0` + `pointer-events: none` pattern gated behind `:hover` (e.g. the old `.radioright` policy descriptions) never triggers on a touch device — the content stays invisible *while still reserving its layout height*, which reads as a big empty gap, not as "content that needs a tap." Fix pattern: add `@media (hover: none) { .foo { opacity: 1; pointer-events: all; } }` rather than redesigning the component. Grep for `:hover` rules that touch `opacity`/`visibility`/`pointer-events` when auditing a page for mobile gaps.

**3. Font Awesome version mismatch.** The site loads FA5 (`static/... use.fontawesome.com/releases/v5.8.2/css/all.css`) plus a v4-shim (added this session, same `<link>` pattern) because some bundled widgets (SimpleMDE's toolbar) hardcode unprefixed FA4 class names (`fa fa-bold`) that don't resolve against FA5's `all.css` alone. If you see a broken/glitchy icon glyph near a third-party widget, check whether it's emitting v4-style classes before assuming it's a CSS specificity bug.

**4. Jinja autoescaping corrupts data embedded in `<script>` blocks if you hand-quote it.** `name: '{{ some_user_string }}'` HTML-escapes apostrophes (`&#39;`) *before* the browser ever parses it as JS, so a value like `Monopoly's Fleet` renders literally as `Monopoly&#39;s Fleet` in the UI. Always use `{{ value | tojson }}` (no manual quotes) when embedding any Python value into a `<script>` block — this is correct for both escaping and quoting.

**5. Stripping a unit instead of relabeling it leaves a bare, unreadable number.** If you're tempted to `.replace(" money", "")` an expense string to avoid a redundant label, prefix a symbol (`$`) instead of stripping to nothing — a bare `479,700` with no context reads as broken, not as "obviously money."

**6. Hardcoded background+text color pairs break silently on theme switch.** A component that sets `background: #1e293b` without also setting an explicit `color:` (relying on the page's `--colorOne` for text) can render text nearly invisible when the site's light/dark theme doesn't match what the author had in mind. Found live on `/military`'s inactive sub-tabs. Grep pattern for an audit: `background: #[0-9a-f]{6}` in an inline `<style>` block or component CSS with no paired `color:` in the same rule.

**7. `static/style.min.css`, if present, silently wins over `static/style.css` for local verification.** `game_ui.py`'s `game_stylesheet_filename()` prefers the minified file whenever it exists on disk. Production always regenerates it fresh at deploy time (`nixpacks.toml` build phase runs `scripts/bundle_game_css.py`), so this is harmless in production — but a locally-committed or locally-stale copy will make your local dev server silently serve old CSS while you edit `style.css`/`static/css/*.css`, making a real fix look like it isn't working. If a local CSS check doesn't reflect an edit you just made, run `python3 scripts/bundle_game_css.py` before assuming the fix is wrong.

**8. `!important` on a shared class can silently lose to a more specific selector elsewhere.** Don't trust a grep-based "no conflicting rule found" — check computed styles / matched CSSOM rules on the live page when a `!important` rule doesn't seem to be applying.

**9. Sitewide `align-items: flex-start` on `.templatedivflex2` silently blocks per-page stretch fixes — the single biggest cause of "dead space" reports.** `static/style.css` has `.templatedivcontent .templatedivflex2 { align-items: flex-start; }` (added 2026-02-03, commit `69381dec`, "Two-column content alignment fix" — a deliberate fix for a *different*, now-unknown problem). Because almost every page-specific two/three-column layout (`.country-overview-grid`, `.province-info-grid`, etc.) *also* carries the bare `.templatedivflex2` class alongside its own class, this sitewide rule (2-class specificity via the `.templatedivcontent` ancestor) outranks a same-specificity single-class page override. The result: whenever two columns hold visibly different amounts of content (a data table vs. a chart, a short table vs. a long one), the shorter column stops exactly at its own content height and the page background shows through below it — reads as "empty space" or "things not filling their box." Two confirmed live instances fixed 2026-08-19: `country.html`'s General/Affairs/Demographics grid (fixed by merging the short columns into the tall one — content rebalancing, no CSS conflict to fight) and `province.html`'s Province Information/Demographic Shape grid (fixed with `align-items: stretch !important` on `.province-info-grid`, since simply setting `stretch` without `!important` silently did nothing — confirmed via `getComputedStyle` before assuming the fix worked). **Do not blanket-revert the sitewide rule** — its original purpose is unknown and past precedent shows it was added to fix a real problem; fix each instance with a scoped, specific override instead. When you see this symptom: check whether the container carries the bare `.templatedivflex2` class, and if `align-items` on your specific selector is being silently outranked before concluding the CSS "isn't working."

**10. Chart.js canvases with `responsive: true, maintainAspectRatio: false` need a real height *cap* on their wrapper, not just a `min-height`.** Chart.js sizes the canvas to fill whatever space its container gives it. If a page-specific override replaces the wrapper's fixed `height` with an open-ended `min-height` (as `.province-info-demographics .chart-wrapper` did — the base `.chart-wrapper` rule has `height: 280px`, the override dropped it to `min-height: 280px` with nothing capping the top), the canvas can grow unbounded the moment anything gives the wrapper more room to expand into (e.g. a sibling column stretching per landmine #9) — producing a huge blank canvas overflowing past its visible card, with whatever axis label Chart.js happened to place inside it appearing to float in empty white space. Fix: always pair a page-specific chart-wrapper override with an explicit `height` (not just `min-height`), and verify via `canvas.getBoundingClientRect().height` matching the intended fixed value, not just "does it look OK once."

**11. Manual `margin-left`/`margin-top` "centering" on an icon inside a fixed-size circular button is a red flag — use real `align-items`/`justify-content: center` instead.** Found on the floating resource-toggle button (`.resourcedivchild`/`.resourceicon`): a `margin-left: 10px` was hand-tuned to roughly center a 46px icon in a 56px circle, with no `align-items`/`justify-content` set on the flex container at all. This kind of fix looks right at the exact size it was tuned for and silently drifts wrong if the icon size, button size, or font ever changes. When auditing a circular/square icon button for "not centered," check for exactly this pattern (a flex container with a lone directional margin on its child, missing one or both of `align-items`/`justify-content`) rather than nudging the margin value further.

**12. When you find one instance of a layout bug, systematically check for the same root cause elsewhere before calling it done — but scope the search to the actual mechanism, not just similar symptoms.** After fixing landmines #9–#11 as one-off instances, a full sweep found the real value: (a) grep every `align-items:\s*start|flex-start` in `static/style.css`+`static/css/*.css`, and for each one actually read the selector's context — most are legitimate icon+text row alignments, only ones on multi-column grid/flex containers holding structurally different content per column are at risk; (b) grep every `new Chart(` call sitewide and check each one's wrapper CSS for a real height cap; (c) script-search for circular flex buttons combining a margin hack with a missing `align-items`/`justify-content`, rather than eyeballing each candidate. This is a repeatable audit, not a one-time fix — worth re-running whenever a new "empty space" or "not centered" report comes in, since it's cheap (all static analysis, no live browser needed) and it's what actually answers "is this the only one" instead of guessing.

## Research-backed rules (full detail + sources in memory, see below)

- **Touch targets:** 44×44pt (Apple) / 48×48dp (Material) minimum hit area — but only for real interactive controls (buttons, links, inputs). Read-only stat chips don't need this; sizing them like buttons wastes space.
- **Thumb zone:** primary actions (Buy/Sell/Research/Submit) belong low/center in a card, not at the top — this is already the pattern in military.html/upgrades.html card layouts; match it in new templates.
- **Contrast:** WCAG AA minimum 4.5:1 normal text, 3:1 large text (≥18pt or ≥14pt bold) and non-text UI components (borders, icons).
- **Dense tables:** this game's real mobile weak point (countries list, coalition members, market). Prefer horizontal-scroll-with-sticky-first-column (already applied to `.templatetable`/`.templatetable2`/`.templatetable3` at the 768px breakpoint) over card-view, since it keeps the identifying label visible while scrolling and shows more rows per screen.
- **Progressive disclosure:** players spend ~80% of attention on gameplay content, ~20% on HUD/chrome. Don't add more always-visible chrome — the existing "tap chip → expand" pattern (resource HUD → All Resources panel) is the right shape; extend it rather than inlining more.
- **Idle-game genre norm:** make current state *and rate of change* glanceable, not just totals — relevant for any future resource-display work.

Full research with sources: Claude memory `ano-mobile-ui-research` (WebSearch-backed, Material/Apple HIG/NN.g/WCAG citations). Standing mobile-first rule + history of *why*: Claude memory `ano-mobile-first-ui`.

## Verification workflow (non-negotiable)

1. **Reproduce the bug live before fixing it** — screenshot the actual broken state on a real account, don't fix from code-reading alone.
2. **Test on Dede's real account**, not a synthetic/throwaway one, whenever his real session is reachable. Only fall back to a fresh signup (local `ano_staging` DB only, never production) when his account genuinely isn't available for the check you need — and delete the throwaway account immediately afterward (see cleanup SQL pattern below).
3. **Verify at real mobile width, device-accurate, not just a narrow window.** `mcp__claude-in-chrome__resize_window` does NOT reliably drive the real rendered viewport in this environment — confirmed 2026-08-19: requests lag by one call (checking `window.innerWidth` right after a resize reads the *previous* request, not the new one) and can get stuck at a floor (~500px) entirely. Don't trust it for device-accurate checks, and don't loop retrying it. Instead: ask Dede to manually open Chrome DevTools' device toolbar (Inspect → toggle device toolbar → pick a real preset, e.g. "iPhone 14 Pro Max", 430×932) on the automation tab, then use `computer` (`screenshot`/`zoom`) and `javascript_tool` against that same `tabId` — this captures the real emulated viewport (confirmed working). Never do this on Dede's real logged-in browsing tab/session, only on the disposable local-dev automation tab; always get a fresh tab from `tabs_context_mcp` rather than assuming one still exists across turns.
4. **Test the whole chain, not just the reported symptom** — what leads into the bug and what happens right after the fix, end to end on a live account. A fix that's locally correct but unreachable (e.g. a cache fix behind a research-tree gate that itself errors) isn't actually fixed yet.
5. **Ship, then re-verify post-deploy.** Poll `/deploy-info` (or `railway status --json`) for the merged commit, then re-run the same live check that reproduced the bug, on the same account, before telling anyone it's fixed.
6. **Never tell a Discord bug reporter something is fixed until it's been verified live on Dede's real account first** — "deployed, should work now" is not verification.

## Local dev + staging DB (for live verification and safe screenshot capture)

- Local Postgres for dev/staging: `postgresql://dede@localhost:5433/ano_staging` (port **5433**, not 5432 — a different, unrelated system Postgres owns 5432). Start if needed: `/opt/homebrew/Cellar/postgresql@14/14.20/bin/postgres -D .local/pgdata -p 5433` (check `pg_isready -h localhost -p 5433` first).
- Run the game against it: `env -u DATABASE_PUBLIC_URL DATABASE_URL="postgresql://dede@localhost:5433/ano_staging" PORT=5050 python3 app.py` (the `-u DATABASE_PUBLIC_URL` unset is a safety guard — that var points at the real production DB proxy). **Stop this process when done** — don't leave it running.
- If a buy/sell action 500s locally with an `UndefinedColumn`/schema-mismatch error, this DB is likely missing migrations, not an app bug: run `env -u DATABASE_PUBLIC_URL DATABASE_URL="postgresql://dede@localhost:5433/ano_staging" python3 scripts/apply_all_pending_migrations.py` (idempotent, local-DB-only when run with this exact env override — never omit the `-u DATABASE_PUBLIC_URL`). Caught and fixed on 2026-08-19 (`production_cost_aluminium` missing from migration 0043, plus several older ones).
- Throwaway account cleanup pattern (run after any signup against `ano_staging`, substituting the real `id`):
  ```sql
  BEGIN;
  DELETE FROM admin_actions WHERE user_id=$ID;
  DELETE FROM advertisements WHERE user_id=$ID;
  DELETE FROM coalition_members WHERE user_id=$ID;
  DELETE FROM col_applications WHERE userid=$ID;
  DELETE FROM col_bank_contributions WHERE user_id=$ID;
  DELETE FROM discord_link_codes WHERE user_id=$ID;
  DELETE FROM map_unit_deployments WHERE user_id=$ID;
  DELETE FROM offers WHERE user_id=$ID;
  DELETE FROM policies WHERE user_id=$ID;
  DELETE FROM poll_votes WHERE user_id=$ID;
  DELETE FROM provinces WHERE userid=$ID;
  DELETE FROM purchase_audit WHERE user_id=$ID;
  DELETE FROM reset_codes WHERE user_id=$ID;
  DELETE FROM revenue WHERE user_id=$ID;
  DELETE FROM upgrades WHERE user_id=$ID;
  DELETE FROM user_buildings WHERE user_id=$ID;
  DELETE FROM user_economy WHERE user_id=$ID;
  DELETE FROM user_military WHERE user_id=$ID;
  DELETE FROM user_tech WHERE user_id=$ID;
  DELETE FROM stats WHERE id=$ID;
  DELETE FROM users WHERE id=$ID;
  COMMIT;
  ```

**Full-suite regression check (2026-08-19):** `pytest tests/` against local `ano_staging` produces 44 failures both before and after this session's migration work — diffed exact failure sets, byte-identical. All 44 are pre-existing local-environment gaps (missing fixture users/data, schema drift beyond what `apply_all_pending_migrations.py` catches up), not caused by the template/macro/token changes. Re-run this diff (stash vs. working tree) after any future migration batch to keep this confidence cheap.

## Mobile polish audit (2026-08-19)

A general mobile audit (real iPhone 14 Pro Max device emulation) of the most-trafficked screens (own country page, province base-view + classic view, military) found and fixed:

1. **Real bug: `.menuflex2` tab bars clip/overlap text instead of wrapping or truncating gracefully.** A site-wide `@media (max-width: 768px)` rule (`static/css/game-layout.css` ~line 492) forces ALL `.menuflex2` tab bars into a single non-wrapping row with `!important`, added by a prior session to stop "endlessly scrolling" stacked layouts. Combined with `white-space: nowrap` labels and no `text-overflow` handling, any label too long for its shrunk chip (e.g. "Air Force", "Revenue") visually overlapped into the neighboring chip instead of wrapping or truncating — looked broken, not just cramped. Fixed two ways:
   - **General fallback** (`game-layout.css`): added `overflow: hidden; text-overflow: ellipsis` to `.menuflex2 .smallheader`, so any page relying on the shared single-row behavior now truncates cleanly with "…" instead of bleeding into its neighbor. This is the safety net for pages without their own custom tab CSS (e.g. `country.html`, `coalitions.html`).
   - **Root-cause fix for `military.html`**: this page already had its own well-designed 2×2 wrap layout (`flex-wrap: wrap`, `flex: 1 1 45%`, comfortable `1rem` font) that the global `!important` rule was silently clobbering. Added matching `!important` to military.html's own rules so its original, better design wins back control — ARMY/AIR FORCE/NAVY/SPECIAL now wrap into a proper 2×2 grid at full readable size, not cropped text in one row. **If any other page has its own per-page `.menuflex2` tuning that looks broken on mobile, check for this exact conflict first** (`!important` vs `!important`, check which one actually renders via computed styles, not just reading the CSS) before assuming the page's own CSS is wrong.
   - Note: the ellipsis fix does NOT apply when the label element itself is `display: flex` (e.g. a label with a notification badge `<span>` next to the text, like province.html's "Public Works" city-tab) — `text-overflow: ellipsis` only works on block-level overflow, not flex containers. Seen once (province.html), left as a minor residual truncation rather than restructuring markup for it.

2. **Real bug: `province.html`'s classic-view "City"/"Land" infrastructure table overflows its container with zero scroll affordance.** The `.menuflex2.width100` category-tab row lives inside a `<table class="templatetable templatetable2 smalltable">` (province.html only, `smalltable` isn't used elsewhere). Because the table used default `table-layout: auto`, a long cell's content (e.g. "Dist. Centers / Food Banks") could stretch the whole table wider than its container — up to 15px past the actual viewport edge on a 430px phone — silently cutting off the "Public Works" column with no indication anything was scrollable, unlike the resource HUD's correctly-faded scroll strip. Fixed by adding `table-layout: fixed` to `.smalltable.templatetable2` (`static/style.css`, pre-marker hand-written section) so columns stay at their declared 33.33% width regardless of content length. Verified: table no longer overflows its container (`scrollWidth === clientWidth` now), the previously-invisible column is visible again.

3. **Data bug, not mobile-specific**: the "Quick Build" dropdown's "Aerodromes" option shows "Aerodromes — Aerodromes" instead of a cost description like every other option ("Army Bases — Army bases cost $8M..."). Found, not yet fixed — flagged for whoever touches `province.py`'s build-option list next.

4. Everything else audited (own-country page, province base-view grid, signup flow) was already genuinely solid — good touch targets (84×84px district hubs, well above the 44×44pt minimum), working scroll-fade affordances on the resource HUD, clean contrast in both themes. Not everything on mobile was bad; these were the specific, concrete breakages.

**Process note**: editing a `templates/*.html` file's inline `<style>` or Jinja does NOT take effect on a running local dev server — Jinja template caching requires a server restart (`debug=off`, no `TEMPLATES_AUTO_RELOAD`) to pick up template changes, unlike `static/css/*.css` changes which apply on next page load after `bundle_game_css.py`. If a template edit doesn't seem to apply live, restart the dev server before assuming the CSS/specificity reasoning is wrong. Also: the dev server does not persist login sessions across a restart — expect to re-signup/re-login after every restart.

## Deploy verification

Production is Railway, deployed from `master`. After merging: poll `https://affairsandorder.org/deploy-info` (JSON `git_commit`) or `railway status --json` (`latestDeployment.status`/`commitHash`) — `/deploy-info` sometimes lags the actual deployed commit, so cross-check both if in doubt. PR branches must be created from fresh `origin/master`, not an old local branch, or squash-merge will report "not mergeable" (fix: `git fetch origin && git rebase origin/master && git push --force-with-lease`).

## Design-system migration tracker

Ongoing per-template migration onto `templates/macros/game_ui.html` (`game_button`/`stat_card`/`game_panel`) and `static/css/tokens.css`, per the design-system consolidation plan. Update this table as each page lands.

| Page | Status | Macros used | Inline `<style>` removed |
|---|---|---|---|
| `statistics.html` | Migrated (pilot) | `stat_card`, `game_panel` | n/a (had none) |
| `intelligence.html` | Migrated | `stat_card`, `game_panel` | n/a (had none); also removed a stray leftover debug divider (`<!-- Remove this -->` + a literal dashed `<h1>`) found while editing |
| `wars.html` | Migrated | `game_button` (new `href`/action-strip support added to the macro for this) | n/a (had none) |
| `military.html` | Migrated (buttons only) | `game_button` (all 24 buy/sell buttons across 12 units) | not touched this pass — the 133-line inline `<style>` is legitimate page-scoped component CSS, already token-based (`var(--foreground)`/`var(--accent)` etc.), not a duplication problem like the other large-style pages. Verified live on real iPhone 14 Pro Max device emulation (430×932, DevTools device toolbar, both themes); a real buy-button click round-tripped correctly to `/military/buy/soldiers` twice — first hit an unrelated pre-existing local-DB schema gap (fixed, see below), then after the fix correctly reached real backend validation ("Unit buy limit exceeded (allowed 0)" — expected for a resourceless throwaway account, not a bug) |
| `country.html` | Migrated (3 of 5 buttons) | `game_button` for "Declare" (war), "Invite to Coalition", "Transfer" — verified live at `/country/id=<other player>` on real device emulation | Not touched: the two Nuclear Strike/Strategic Airstrike buttons keep their hardcoded bright red/orange inline colors deliberately — that's intentional high-stakes-action emphasis matching their section headers' colors, not theme debt; forcing them onto the standard `--danger` token would visibly mute them and is a design call, not a mechanical fix. The 177-line inline `<style>` (Interactive Events glassmorphism modal) uses `color: inherit` + translucent whites throughout — already theme-agnostic by design, not a bug, left alone. The 38 raw `stat-card` blocks already use correct classes (just not macro-ized); skipped bulk-converting them since the markup wasn't uniform enough for a safe scripted pass and there's no visual bug to fix |
| `province.html` (buttons pass — first of its multi-batch migration) | Migrated | `game_button` for 93 of 95 buttons (all buy/sell/build/purchase actions across every resource/building type, plus the two city/land "Purchase" buttons and the "Build" button) | **Real bug caught and fixed during this pass, worth remembering for any future scripted button conversion**: this page's `formaction` values contain a dynamic Jinja expression (`formaction="/buy/coal_burners/{{ province['id'] }}"`), not a static string. A naive regex-based conversion (same script that worked fine on `military.html`, which only has static formactions) produces `game_button(..., formaction='/buy/coal_burners/{{ province['id'] }}')` — **invalid**: you can't nest `{{ }}` inside an already-open `{{ }}` expression, and the inner `'` quotes in `province['id']` also collide with the outer quoted string. Correct form: `formaction='/buy/coal_burners/' ~ province['id']` (Jinja string concat with `~`). Caught via `app.jinja_env.get_template()` compile-check plus reading the actual generated macro-call text before trusting it — a plain compile-check might not have caught the quote-collision variant, so also grep the generated file for stray `{{`/mismatched quotes after any scripted conversion touching dynamic formactions. Verified live: created a real province, confirmed the rendered `formaction="/buy/coal_burners/55"` had the correct real ID, and a real Buy POST round-tripped with a clean `302` (not 400/500). Left alone (2 buttons): the disabled Nuclear Reactor buy/sell pair (`templateclosedbutton nuclearreactordisabledbutton` classes, `disabled` attribute, prerequisite-gated) — a genuinely different disabled-with-tooltip component shape, not worth a macro for 2 instances. **Still open for this page** (per the plan, its own multi-PR batch): the 863 `class=` attributes overall mean plenty of `templatedivflex2`/other markup remains unmacro'd, and `game-experience.css` still needs splitting out of its province-scoped selectors — not done this pass |
| `market.html` | Migrated (buttons only) | `game_button` | not touched this pass |
| `coalitions.html` | Migrated (submit button only) | `game_button` | has a large inline `<style>` block at the top — not touched this pass, candidate for the "large inline `<style>`" bucket later |
| `countries.html` | Migrated (submit button only) | `game_button` | not touched this pass |
| `find_targets.html` | Migrated (filter button only) | `game_button` | not touched this pass |
| `countries.html` | Additionally cleaned up | n/a | pagination `<style>` block's 7 hardcoded `#00a7e1` occurrences replaced with `var(--accent)` (identical value in both themes, zero visual change, verified via render diff) |
| `rankings.html` | Reviewed, no fit | — | pure tables, no stat-card/button pattern; 4 near-identical rank/nation/value tables are a real but single-page-only data point for a future table macro, not enough evidence yet to build one |
| `account.html` | Reviewed, paused | — | inline `<style>` is mostly page-specific layout (delete-account modal, Discord-link panel), not token duplication. Found two pre-existing bugs while reading it: an orphaned/invalid CSS fragment (`min-width: 120px;` + stray `}` with no selector, right after the `.account-action-form button.templatedivbutton` rule, ~line 358) and a fully-shadowed duplicate `.account-action-form` selector (row layout at ~341, later overridden by a column layout at ~428 — the row version is dead code). Also: `.modal-content` hardcodes dark bg+light text (`#1a1a2e`/`#eee`/`#ccc`/`#fff`) for the delete-account confirmation modal, so it doesn't follow the site's light/dark toggle — paired correctly so not literally invisible, but a real theme-inconsistency. Left alone pending a decision on whether that modal should become theme-aware or stay a deliberately distinct treatment. |
| `assembly.html` | Reviewed, paused | — | Entire 210-line inline `<style>` is a bespoke glassmorphic dark treatment (custom gradients/hex colors) for the World Assembly voting UI that ignores the site's theme tokens entirely — always dark regardless of site theme. This is a design-direction call (make it theme-aware vs. treat as an intentional STYLE_BIBLE "Vivid" moment), not a mechanical extraction — see the plan's note about doing a gut-check with Dede before applying/removing vivid treatments. |
| `world_map.html` | Deliberately skipped | — | Phaser/PixiJS canvas HUD overlay, permanently dark by design (glass control panel over a game canvas) — matches the plan's note that this page is outside STYLE_BIBLE's scope and should stay separate |

`game_button` gained an `href` param (renders `<a>` instead of `<button>`) and a configurable `extra_class` (default `templatecenteredbutton`) after finding a second real button shape — `class="center templatedivbutton [smallactionbutton]"`, seen 10x across the 5 files above — that didn't fit the original hardcoded class. Verified backward-compatible with the original province.html shape before use.
