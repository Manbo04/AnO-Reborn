# Unique Nation Traits + "The Golden Throne" (plan, awaiting approval)

Status: BUILT (PR #250). Branch: `unique-nation-traits`.

**Changes after Dede's review (2026-11-03):** the pilgrim offering is population only (the $250,000 money option was removed), and the Wall of the Spent records and shows how many people each nation gave (`throne_pilgrimages.people`).

## 0. Decisions I need from you (defaults chosen, "approve" accepts all)

1. **Untargetable vs. defense.** Your nation is now untargetable (PR #247), so nobody can attack it. The Astronomican shield and the crisis defense penalty would therefore change nothing in a fight. Default: keep you untargetable; the defense modifier is still computed and **shown** on the page, and only takes effect if you ever lift `untargetable`. The *happiness* effects are real.
2. **10 souls is flavor, not a lever.** You have ~59M population; 10 people a day never runs out. Default: the sacrifice is always 10 souls (lore number), but the *gameplay* lives in Vitality, which drains a little every dawn (the Throne devours) and is topped up by **other players' pilgrims**. If nobody comes, Vitality sinks slowly (about 60 days from 60 to 0). If players show up, it rises. So the community, not you, decides how strong the Throne is.
3. **Artwork.** You attached three Warhammer 40k artworks. Those are Games Workshop's copyrighted art; hosting them on a public site risks a takedown, and the files are not on disk anyway. Default: original CSS/SVG banner (skull-sigil, gold/crimson/black, no copied art). If you want real images, give me file paths and say you accept the risk.
4. **Nation name.** Your nation is named "Dede". Default: unchanged; the page header shows the title "Holy Terra - Seat of the Golden Throne" from the trait. Renaming is a separate decision.
5. **No motion.** Motion makes you ill (see PR #246). Everything here is static: the bar fills statically, no glow/pulse/scan/animation. The countdown is plain text refreshed once a minute.

## 1. Generic trait system (reusable)

Config-driven; adding a trait = one config entry + one handler module.

- `app_core/traits/registry.py`: `TraitHandler` interface and registry:
  - `daily_tick(db, user_id, now)` - run once per dawn per nation holding the trait
  - `modifiers(db, user_id) -> dict` - e.g. `{"happiness_pct": 3, "food_mult": 0.75}`
  - `page_context(db, user_id, viewer_id) -> dict` and a template partial name
- `app_core/traits/config.py`: `TRAIT_ASSIGNMENTS = {1: ["golden_throne"]}` (user_id -> trait keys). A boot/tick sync upserts these into `nation_traits`; removing an entry disables the row (never deletes history).
- `app_core/traits/modifiers.py`: `get_modifier(db, user_id, key, default)`. Tolerant of unmigrated tables (same pattern as `app_core/vacation.py`) and a per-request cache, so nations without traits pay ~0 extra queries.
- Page hook: `countries.py` adds `traits` to the context; `country_v2.html` loops `{% for t in traits %}{% include t.partial %}{% endfor %}`.

## 2. Data model (all migrations additive, `IF NOT EXISTS`, no backfills, safe to re-run)

| Table | Columns |
|---|---|
| `nation_traits` | `user_id`, `trait_key`, `enabled`, `state JSONB`, `created_at`; PK `(user_id, trait_key)` |
| `throne_state` | `user_id PK`, `vitality NUMERIC(5,2)`, `vigil_start DATE`, `last_dawn DATE`, `souls_total BIGINT`, `crisis BOOL`, `active_event TEXT`, `event_ends_at TIMESTAMPTZ` |
| `throne_days` | `day DATE PK`, `souls_own INT`, `souls_pilgrim INT`, `vitality_after NUMERIC`, `event TEXT`, `skipped BOOL` |
| `throne_pilgrimages` | `id`, `day DATE`, `pilgrim_user_id`, `weight INT`, `cost_kind TEXT`, `created_at`; **UNIQUE `(day, pilgrim_user_id)`** |
| `throne_blessings` | `user_id PK`, `expires_at`, `pct NUMERIC` (one row per nation: refreshed, never stacked) |

New columns on existing tables: none. Snapshot refresh of `db/` after the migration ships needs your guard code again (same as #244).

## 3. Tick hook

- New Celery task `tasks.task_nation_traits`, every 10 minutes, idempotent, UTC schedule in `celery_schedule.py` (env-overridable like the others).
- "Dawn" = **06:00 Europe/Vilnius** (fixed, so the countdown is predictable; real sunrise drifts). The task asks "is Vilnius-local `today` > `last_dawn` and time >= 06:00?". Then it takes `SELECT ... FOR UPDATE` on `throne_state` and inserts `throne_days(day)` with `ON CONFLICT DO NOTHING`. Two workers or a retry cannot run a dawn twice.
- Dawn steps: (1) tally yesterday's pilgrimages (weight sum); (2) souls from pilgrims offset the 10 first, the rest come from Holy Terra's population (taken from the largest provinces, never below 1 pop per province); (3) vitality update (section 4); (4) crisis/recovery; (5) maybe roll a Throne event (section 6); (6) write `throne_days`; (7) expire stale blessings/events. A skipped sacrifice (population under the config floor) is recorded as skipped.
- Kill switch: env `NATION_TRAITS_DISABLED=1` (same convention as bot nations).

## 4. Vitality math (every number lives in `app_core/traits/golden_throne_config.py`)

Start 60. Each dawn: `delta = -4 (Throne devours) + 3 (full own+pilgrim sacrifice made) + 0.5 * min(pilgrim_weight, 10)`, clamped to 0..100.
- 0 pilgrims: -1/day. 2 pilgrims: 0 (break-even). 10+ pilgrims: +4/day. (Corrected during the build: an earlier draft said 6.) Skipped sacrifice: -4 -3 extra penalty.

| Vitality | State | Effect (modest) |
|---|---|---|
| 80-100 | Blazing | happiness +3%, defense +5% |
| 40-79 | Steady | happiness +1%, defense +2% |
| 15-39 | Flickering | happiness -2%, warning text |
| 1-14 | Failing | happiness -5%, defense -5%, food production -5% |
| 0 | **The Emperor's Light Fails** (crisis) | happiness -10%, defense -10%; decay is paused, +3/day from the sacrifice; ends at vitality >= 20 |

In-character warnings: "The Throne flickers...", "The Golden Light gutters.", "The Emperor's Light Fails." Shown on the page and logged via `log_event`.

## 5. Pilgrims (the interaction for other players)

Route `POST /traits/golden-throne/pilgrimage` (CSRF'd, `login_required`), button on your nation page.
- Choose cost: **1,000 population** from the pilgrim's own nation, or **$250,000** (burned, not paid to you, so it is never a gift or a transfer).
- Counts as 1 soul toward tomorrow's sacrifice (2 during Pilgrim Surge).
- Pilgrim blessing: **+2% happiness for 24h** on the pilgrim's nation, refreshed not stacked. Their nation is carved on the Wall of the Spent.
- Validation, all server-side: not yourself; not a bot; account age >= 2 days; once per Vilnius day (the UNIQUE row **is** the limit, taken in the same transaction as the cost deduction, so double-clicks, two tabs and races cannot double-spend); amount fixed server-side (no client numbers); cost deducted through `app_core/economy/ledger.py`; population cost never takes a province below its floor.
- **Interplay with PR #247:** your nation is `untargetable`, but pilgrimage is a beneficial offering, not an attack, so this route is explicitly exempt from the untargetable guard.
- Reversal: none needed. It is a one-day donation with a built-in cooldown; the blessing expires itself.

## 6. Hive City trait (permanent modifiers via `modifiers()`)

Population capacity per province +25%, industry output +10%, food production -25%, building upkeep +15%. Net effect: dense and productive but dependent on imports, with higher costs. Exact insertion points (province population cap, production in revenue tick, food tick, maintenance tick) are confirmed against the live formulas before I edit; if a formula cannot take a clean multiplier I will say so rather than hack it.

## 7. Throne events (about 1 per week)

At each dawn roll `1/7`; at most one active, minimum 5 days apart. Each is announced on the page with a banner line and logged in world events.
- **Whispers from the Throne:** one random small bonus for 24h (+2% happiness, or +5% industry, or +3 vitality).
- **Heretic Uprising:** -5% happiness for 24h, -3 vitality.
- **Pilgrim Surge:** pilgrim weight x2 for that Vilnius day.

## 8. UI (mobile-first, 390px first)

New partial `templates/partials/traits/golden_throne.html` + `static/css/trait-golden-throne.css` (added to the bundle; run `scripts/bundle_game_css.py`):
- Banner (original SVG/CSS, gold/crimson/black), "Day N of the Vigil", vitality bar (static fill + label + state text), "Next sacrifice in 7h 12m", active event line, blessing status for the viewing player, the **Send pilgrims** card (cost choice, disabled with reason when already sent / not logged in).
- **Wall of the Spent:** scrollable list (newest first, 40 per page, "Load more" via `GET /traits/golden-throne/wall?before=<day>`), each day: souls own / pilgrim, which nations gave pilgrims, plus a live total-souls counter. Public JSON, rate-limited, read-only.
- Reachable: your nation page (id 1) always has it. Because you are hidden from the `/countries` directory, I will add a pinned "Holy Terra" card at the top of `/countries` that links to your page, so players can find it.
- Empty states: day 0 (no sacrifices yet), no pilgrims, logged-out viewer (shows "Log in to send pilgrims").

## 9. Why it is balanced

- You are hidden from rankings and untargetable, so the bonuses cannot win you anything competitive; the bonuses are small (max +3% happiness) and the hive trade-offs cost real food and upkeep.
- Pilgrim blessing is +2% happiness, 24h, non-stacking, costs real population or money, once per day per account: farming alts gives nothing worth the cost.
- The Throne's strength is controlled by other players' choices, not yours; nothing is purchasable with real money.
- All numbers in one config file; a single env kill switch.

## 10. Build + verification plan

Small commits: (1) migration + registry/config, (2) golden throne tick + vitality math, (3) pilgrimage route, (4) modifier hooks (happiness, food, industry, upkeep, defense), (5) UI partial + CSS + wall, (6) events, (7) tests/docs/session log.
Tests (DB-free where possible, same style as `tests/test_visibility_untargetable.py`): vitality math table, dawn idempotency (two runs = one dawn), skipped sacrifice, crisis entry/exit, pilgrim limits (once per day, self, bot, age, race via the UNIQUE row), blessing refresh not stack, modifier lookup tolerant of missing tables.
Live verification in Chrome, desktop and 390px, as your nation (read-only view) and as test account 16 (send pilgrims, see blessing, see the Wall update), screenshots attached to the PR. If I can't sign in as account 16 with the existing recipe, I will ask you rather than guess. PR is opened but **not merged**.
