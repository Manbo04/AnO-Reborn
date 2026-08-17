---
name: ano-ui-design
description: Visual identity, design tokens, verification workflow, and known bug patterns for Affairs and Order (AnO-Reborn). Consult this before creating or modifying ANY template/CSS in this repo — mobile-first, keep faith with the existing look, don't redesign.
---

# Affairs and Order — UI Design Skill

This is Dede's living game, not a blank canvas. Every rule here came from a real bug report, a real correction, or a real research pass — not from general design taste. Read this before touching `templates/*.html` or `static/css/*.css`, and re-check the relevant section whenever a fix seems to require a new color, new component, or new pattern instead of reusing what's here.

## The one mandate that overrides everything else

**Mobile-first, and keep faith with the current look.** Most players are on phones/tablets. Every change is designed and checked at mobile width (~390px) FIRST, then scaled up — never the reverse. And this is an incremental, audit-driven fix pass on an *existing* visual identity, not a redesign brief: reuse the token system and component classes below rather than inventing new colors, fonts, or component shapes. If you think a fix needs a new visual pattern, it almost always doesn't — look harder for the existing class/token that already does the job.

This directly overrides the generic `frontend-design` skill's instinct to "take an aesthetic risk" — don't, here. That skill is for greenfield pages with no existing identity. This game has one; the risk-taking already happened and shipped.

## Visual identity (design tokens — use these, don't invent new ones)

Defined in `static/style.css` (hand-written section near the top, `.theme-light` / `.theme-dark` blocks around line 352+). The site supports both themes; always check a color choice against **both**, not just whichever theme you happen to be looking at.

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

**Dark theme** (same variable names, swapped values) — `--background: #13171e`, `--foreground: #1c2029`, `--colorOne: #e0e4ea`, `--accent: #00a7e1` (constant across themes — this is *the* brand color), `--gold: #e0b84d`, `--success: #3ab87e`, `--danger: #e05a4d`. Full block: `static/style.css` `.theme-dark { ... }`.

**Spacing / radius / layout scale** (`:root` further down, `static/css/game-shell.css` bundle):
- Radius: `--game-radius-sm: 8px`, `-md: 12px`, `-lg: 16px`, `-xl: 24px`
- Space: `--game-space-xs: 4px`, `-sm: 8px`, `-md: 16px`, `-lg: 24px`, `-xl: 32px`
- Breakpoints in active use: `768px` (tablet), `720px`/`750px`/`800px`/`856px`/`1055px` (assorted component-specific — check for an existing `@media` block near the component you're editing before adding a new breakpoint)

**Typography:** `Roboto` (body/UI, loaded via Google Fonts), `Material Icons` / `Material Icons Outlined` (primary icon set — prefer these), Font Awesome 5 (`fas`/`far`/`fab` classes — secondary icon set, used in older templates and by third-party widgets like SimpleMDE).

**Established component classes** — reuse these, don't rebuild:
- `.templatedivflex2` / `.templatedivflex2left` / `.templatedivflex2right` — the standard two-column content layout
- `.templatetable` / `.templatetable2` / `.templatetable3` — data tables, already have mobile overflow + sticky-first-column rules at the `768px` breakpoint
- `.templatedivbutton` — standard button
- `.templateselect` / `.templatetextarea` / `.imageinput` — form controls
- `.stat-grid` / `.stat-card` / `.stat-label` / `.stat-value` — the resource/stat card grid used throughout country/province/military pages
- `.radiodiv` / `.radioleft` / `.radioright` — the toggle-with-description list pattern (National Policies etc.) — note the touch-device fix below before reusing as-is
- `.game-panel-grid`, `.game-stack` — shared responsive panel utilities (`static/css/game-layout.css`)
- Edge-fade on horizontally-scrolling strips: `mask-image: linear-gradient(to right, black calc(100% - 28px), transparent 100%)` — established pattern (tab bars, resource HUD strip), reuse rather than a hard visual cutoff

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
3. **Verify at real mobile width** (~390×844, matching actual device screenshots) — not just desktop with the window narrowed, and not Chrome DevTools device-toolbar toggled on Dede's real browser (this has accidentally happened from automation tool calls before; if using `mcp__claude-in-chrome__*` tools, always use a fresh tab from `tabs_context_mcp`, never assume a tab still exists across turns).
4. **Test the whole chain, not just the reported symptom** — what leads into the bug and what happens right after the fix, end to end on a live account. A fix that's locally correct but unreachable (e.g. a cache fix behind a research-tree gate that itself errors) isn't actually fixed yet.
5. **Ship, then re-verify post-deploy.** Poll `/deploy-info` (or `railway status --json`) for the merged commit, then re-run the same live check that reproduced the bug, on the same account, before telling anyone it's fixed.
6. **Never tell a Discord bug reporter something is fixed until it's been verified live on Dede's real account first** — "deployed, should work now" is not verification.

## Local dev + staging DB (for live verification and safe screenshot capture)

- Local Postgres for dev/staging: `postgresql://dede@localhost:5433/ano_staging` (port **5433**, not 5432 — a different, unrelated system Postgres owns 5432). Start if needed: `/opt/homebrew/Cellar/postgresql@14/14.20/bin/postgres -D .local/pgdata -p 5433` (check `pg_isready -h localhost -p 5433` first).
- Run the game against it: `env -u DATABASE_PUBLIC_URL DATABASE_URL="postgresql://dede@localhost:5433/ano_staging" PORT=5050 python3 app.py` (the `-u DATABASE_PUBLIC_URL` unset is a safety guard — that var points at the real production DB proxy). **Stop this process when done** — don't leave it running.
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

## Deploy verification

Production is Railway, deployed from `master`. After merging: poll `https://affairsandorder.org/deploy-info` (JSON `git_commit`) or `railway status --json` (`latestDeployment.status`/`commitHash`) — `/deploy-info` sometimes lags the actual deployed commit, so cross-check both if in doubt. PR branches must be created from fresh `origin/master`, not an old local branch, or squash-merge will report "not mergeable" (fix: `git fetch origin && git rebase origin/master && git push --force-with-lease`).
