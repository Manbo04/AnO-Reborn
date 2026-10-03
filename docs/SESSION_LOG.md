# AnO-Reborn Session Log

Chronological log of debugging/feature sessions on this repo, moved out of CLAUDE.md on 2026-08-19 to keep the AI guidance file lean. Newest entries were originally at the top of CLAUDE.md; order below is as-authored (not strictly chronological — some sessions were appended out of date order in the original file).

---

### Session: 2026-10-03

**Task**: Discord Scan Bug Fixes & Suggestions (Reported in past 8-24h)

**What Was Done**:
- **Discord Scan**: Scanned Affairs and Order Discord forum and text channels (`bug-reports`, `suggestions`, `general`, `chat`, `ask-the-bot`) for recent player issues and suggestions.
- **Treasury draining with positive net profit & Coalition tax on net income**:
  - Preloaded user building upkeep in `app_core/game_ticks/taxes.py` and taxed `taxable_profit = max(0, money - upkeep)` so alliance tax is on net profit after upkeep, preventing bankruptcy on members with positive gross tax but high upkeep.
  - Updated `countries.py` tax deduction calculation to deduct tax from net profit after building upkeep.
  - Updated `templates/coalition.html` and `templates/coalition_v2.html` descriptions.
- **Happiness Stuck at 3% ("they say it'll make you happy. they lie")**:
  - Exposed unemployment penalty (>30% unemployment docks 10 happiness per tick) in `app_core/economy/province_effects.py` and `province.py`.
  - Added power awareness (`has_power`) to `province_stat_breakdown`; unpowered energy-consuming buildings are now marked `Unpowered` with 0 net effect.
  - Displayed `Unpowered` badge in `templates/partials/province_info.html`.
- **Battle History Notifications for Defender**:
  - In `wars/routes.py`, regular combat now records battle reports in the `news` table for both defender and attacker detailing combat domain, casualties on both sides, victory/defeat outcome, and war conclusion notice if war ended.
- **Remove Citizen Army for Naval and Air Attacks**:
  - In `wars/routes.py`, citizen militia defense is now strictly limited to ground domain (`war_domain == "ground" or war_domain is None`). Air and naval assaults no longer face citizen army militias.
- **World Assembly Formatting & Vote Indicators**:
  - In `templates/assembly.html`, added `white-space: pre-wrap;` to resolution descriptions to preserve formatting and line breaks.
  - Added vote progress bars and vote breakdown counts (For, Against, Abstain, % in favor) to open proposals and past resolutions.
- **Province Demographics Chart Blanking Fix**:
  - In `static/province-demographics.js`, replaced brittle one-shot `load` listener with a resilient polling retry loop (up to 30 attempts at 100ms) with visibility detection (`canvas.offsetParent !== null` and non-zero dimensions) and tab switch integration.
- **News Seen / Read Status & Migration**:
  - Implemented `is_read` column tracking on `news` with index (`migrations/0100_add_news_is_read.sql`).
  - Added unit test coverage `tests/test_news_seen_status.py` and `tests/test_monetary_net_deficit.py`.

---

### Session: 2026-07-05

**Task**: Production outage — 502 sitewide

**What Was Done**: `prod-validator` (the Postgres service) got a stray `railway up` at 09:34 UTC that replaced postgres:17 with a crash-looping app build. Rolled back to the June 7 postgres:17 deployment via Railway GraphQL (`deploymentRedeploy`); postgres logged a clean shutdown → no data loss; site down ~09:35–10:34 UTC. Relinked repo CLI to `web`; added the warning section at the top of this file. Also: granted admin panel to Terra Homeworld via `SUPER_ADMIN_USER_IDS` env on web (69697588); tutorial fixed for real (second missing var `tutorial_constants`, verified 200 + 10 chapter videos rendering).

**What To Watch**: lock the prod-validator service source in the Railway dashboard (only Dede can); consider renaming it to postgres-db. Name-based "Terra Homeworld" admin bypass in `admin_only_guard` should be removed now that the ID allowlist covers him.

---

### Session: 2026-07-04

**Task**: Ticket-0020 ghost account, signup hardening, tasks.py refactor fallout, province UI overhaul

**What Was Done**:
- **Ghost session root cause** (player Kurai, uid 69697638): failed Discord signup rolled back the users row but left session["user_id"] set; `_maybe_org_handoff` then hijacked every retry into auth_handoff, locking them out of the signup form. Fixed: session set only after commit, auth_handoff verifies uid exists, before_request self-clears dead sessions, handoff never overrides signup-form redirects (`96598821`)
- **Signup hardening** (`0cc74736`): all 3 signup paths share init_user_game_data; referral bonus wrapped in SAVEPOINTs; commit+verify+retry before login; ensure_user_provisioned self-heals on all login paths; backfill task extended
- **CI/deploy unblock** (`708de0ea`): 31b929a5 swept email_utils.py + init_db_railway.py into untracked debug_scripts/ — restored both (email_utils is imported by signup/login/change; init_db_railway is run by CI)
- **Celery fallout from game_ticks refactor**: leader_only wrapper lost __module__ → all leader-locked tasks unregistered, economy frozen (`60cd86ff`); market_bot_fight_wars NameError on app — latent since before refactor (`8d75ead2`); BOT_API_SECRET copied to celery-worker service env. Verified: global_tick + refresh_bot_offers succeeded 14:10/14:25 UTC
- **Province UI**: photo-as-card banner lists (`c55457bb`), province.jpg 538KB→204KB progressive (`67fd7972`), theme-aware dock + aligned Build buttons (`42693f27`), light header text + hub/scenery fixes (`2285e978`), command-map redesign: rings + dotted spokes, scenery/blob removed, biome palettes brightened (`e7e95e06`)

**Player Feature Requests (2026-07-04, from Sirius/Terra Homeworld — Dede said "eventually, not right away")**:
- Small flag badge in the corner of the nation view banner
- Custom nation banner background: NOTE half-built already — users.bg_flag column + upload handling exist in countries.py (~line 1391), but the Edit tab has no bg_flag_input field and .countryimagediv hardcodes tundra.jpg; finishing = add form field + render bg_flag as the banner background

**What To Watch**:
- rankings/statistics `cache_response(public=True)` (`40410dda`) is a cross-user leak: layout.html bakes session chrome (own-country link, admin menu) into a shared cache slot — revert public=True or cache data, not pages
- Original signup-crash exception never recovered from logs; if a signup 500s again the traceback will now surface cleanly ("Discord signup error" in web logs)
- backfill_missing_resources now CROSS JOINs users×resources every run (correct via ON CONFLICT, wasteful at scale)
- venvs untracked but still on disk; debug_scripts/ remains untracked

---

### Session: 2026-06-03

**Task**: My Coalition tab 500 (`/my_coalition` → `/coalition/{id}`, error id `a6z4rc2miwgvtwbv2jkw-1780517862`)

**What Was Done**:
- Fixed `coalition()` in `coalitions.py`: stats + member-list `db.execute` blocks used plain `"""` with `{_members_tbl()}` — Postgres got invalid SQL; member fallback could still 500
- Converted those queries to `f"""`, broadened member-fetch failure handling to empty list
- Fixed `adding()` / `delete_coalition()` mistaken `or "{_members_tbl()}"` table name string
- Added `tests/test_coalition_sql_fstrings.py` offline regression
- Branch `cursor/fix-my-coalition-500-a503`, commit `a0c34ead`, PR #55

**What To Watch**:
- Merge PR #55 and redeploy; verify logged-in coalition members see coalition page (not global 500)
- Players without membership should still see “No coalition yet” (`tests/test_my_coalition_empty.py`)

**Next Steps**:
- Production smoke on test account 16 after deploy

---

### Session: 2026-05-22 (follow-up verification)

**Task**: Follow-up verification and remaining security items

**What Was Done**:
- `action_loop.build_structure`: province ownership check (defense-in-depth)
- `coalitions.py`: `_members_tbl()` dynamic SQL; `remove_bank_request` + `set_tax_rate` IDOR fixes; bank routes use `_require_coalition_member`
- `helpers.validate_post_origin` + `require_post_origin` on coalition bank POSTs and `build_structure`
- `scripts/verify_post_deploy.py`; CI `integration-db` job with Postgres + coalition/schema tests
- `tests/test_coalition_membership_guard.py`: cross-coalition `remove_bank_request` test

**What To Watch**:
- Run `DATABASE_PUBLIC_URL=... python3 scripts/apply_schema_compat.py` on Railway if not already applied
- Ops: confirm Railway logs clean for `coalitions_legacy` / `discord_id` errors
- `verify_post_deploy.py` may WARN (403) from Cloudflare on automated clients; fails only on HTTP 500

---

### Session: 2026-05-24 (backend pristine + login fix)

**Task**: Backend log plan implementation; fix login 500 (not homepage).

**What Was Done**:
- **Login P0**: `_ensure_policies_row()` — old code did `SELECT education,soldiers` then `INSERT` on any error → duplicate key 500; bcrypt failures no longer 500
- **CSRF**: explicit `csrf_token` on login, signup, forgot/reset password forms; `scripts/check_csrf_forms.py` in CI
- **Logs**: `docs/logs/README.md`, `scripts/analyze_railway_logs.py`, `docs/BACKEND_LOG_TRIAGE.md`
- **Migrations**: `apply_all_pending_migrations.py` adds 0019/0020 + `schema_migrations` tracking
- **Schema**: split `ensure_schema_compat` per-table steps; province demographic alters tolerate failures
- **Ops**: `docs/CELERY_BEAT_RUNBOOK.md`; CI progression health strict when DB secret set; integration-smoke + `test_login_post.py`
- **diagnose_all_routes**: login user/policies SQL probes

**Commits**: (push to master for Railway deploy)

---

### Session: 2026-05-24

**Task**: Deep fix plan — 500s, economy reliability, security (full implementation).

**What Was Done**:
- **Phase 0**: `schema_compat_succeeded()`, `/ready` checks (DB, resource_dictionary, revenue task age), `scripts/diagnose_schema.py`
- **Phase 1**: PR #49 base + market `give_resource` pool fix, wars peace IDOR fix, `citycount` normalization, template JSON CI script, integration-smoke workflow
- **Phase 2**: `tax_income`/`population_growth` last_run after commit; revenue fail-fast on batch errors; trade agreements xact advisory lock; `task_tax_income` deadlock retries; Sentry on `handle_exception`
- **Phase 3**: Flask-WTF CSRF + SameSite=Lax, reset code 24h TTL, OAuth state fail-closed, `BOT_API_SECRET` required on Railway, session regeneration on login
- **Phase 4**: `scripts/apply_all_pending_migrations.py`, `init_db_railway` migration note, deprecated `add_database_indexes.py`
- **Phase 5**: `test_war_peace_authorization.py`, `check_legacy_schema_refs.py`, CI wiring, conftest `WTF_CSRF_ENABLED=False` for tests

**Deploy**: merge to `master` and push — Railway auto-deploys (GitHub PR optional).

**Ops after deploy**:
```bash
DATABASE_PUBLIC_URL=... python3 scripts/diagnose_schema.py
DATABASE_PUBLIC_URL=... python3 scripts/diagnose_all_routes.py 16
DATABASE_PUBLIC_URL=... python3 scripts/apply_all_pending_migrations.py
```

---

### Session: 2026-05-23

**Task**: Password reset HTTP 500 (`/reset_password/<code>`)

**What Was Done**:
- `set_user_password()` in `database.py` — updates `hash` and/or legacy `password` columns; sets `auth_type='normal'`
- `_ensure_reset_codes_table()` in `ensure_schema_compat()`
- `change.py` reset flows use shared helper; `login.py` accepts byte-stored password hashes
- Tests: `tests/test_password_reset_submit.py`
- PR **#47** (`cursor/fix-password-reset-500-5a73`)

**What To Watch**:
- After merge/deploy: full flow Account → reset link → new password → login
- Users who only used Discord login need `auth_type` flip (now automatic on reset)

---

### Session: 2026-05-22 (Discord bot Phase 1)

**Task**: AnO-native Discord bot (Locutus-style Phase 1)

**What Was Done**:
- Migration `0022_discord_bot.sql`: `discord_link_codes`, guild settings tables (Phase 2), unique `users.discord_id`
- `bot_api.py`: `/api/bot/register`, `/me`, `/nation`, `/wars`, `/resources` (BOT_API_SECRET auth)
- Account page: `/generate_discord_link_code` + UI; OAuth link hardened in `signup.py`
- `discord_bot/` service: slash `/register`, `/me`, `/nation`, `/wars`, `/resources`
- `tests/test_bot_api.py`, `scripts/apply_discord_bot_migration.py`, Railway docs

**What To Watch**:
- Run `python3 scripts/apply_discord_bot_migration.py` on production after web deploy
- Set `BOT_API_SECRET` on web + discord-bot Railway services; `DISCORD_BOT_TOKEN` on bot service
- Start command for bot service: `python -m discord_bot.main`

---

### Session: 2026-05-23

**Task**: Complete progression audit follow-up — revenue commit path fix + merge to master

**What Was Done**:
- Fixed `generate_province_revenue()` in `tasks.py`: defer `last_run` until after commit; resource upserts before education with SAVEPOINT + `MAX_INT_32` clamps; set `user_economy.updated_at = now()` on upsert
- Added `tests/test_revenue_commit_path.py`; CI includes progression audit + revenue regression tests
- Updated `PROGRESSION_AUDIT_2026-05-22.md` with post-fix verification (economy `updated_at` 2026-05-23 09:36 UTC)
- Merged `cursor/progression-audit-fe3b` → `master` (commit `442c41dc`) — Railway auto-deploy

**What To Watch**:
- After deploy: hourly `user_economy.updated_at` should advance without manual trigger (`scripts/progression_health_check.py`)
- `global_tick`, `execute_trade_agreements`, `population_growth` still stale on beat — restart Celery beat + workers
- Do not mount wrong Railway volume `postgres-volume` (use `postgres-2026-05-08` snapshot only)

---

### Session: 2026-05-24

**Task**: Document and harden Next.js ↔ legacy schema bridge (post live DB repair)

**What Was Done**:
- `ensure_schema_compat()` skips `ALTER TABLE users` / provinces demographics when those names are **views** (`users_is_compat_view()`)
- Added `scripts/apply_nextjs_compat_views.py` (introspective `CREATE OR REPLACE VIEW` for User/Nation/Province → users/stats/provinces)
- Updated `scripts/diagnose_database_schema.py` to exit 0 for **BRIDGED** (Prisma + legacy views)
- `migrations/0024_nextjs_compat_views.sql` + `docs/DATABASE_SCHEMA_DECISION.md` bridge section
- Tests: `tests/test_schema_compat_helpers.py` for view detection

**What To Watch**:
- Production `/deploy-info` `schema_compat` should flip to `ok` after redeploy (was `failed` when ALTER hit views)
- Re-run `apply_nextjs_compat_views.py` if Prisma column names differ from defaults
- Full player restore from `postgres-active-data` still needs an explicit migration plan

**Debug follow-up (same day)** — why fixes never reached players:
- **Mistake**: PR #51 left on branch; production stayed on `d7015adc` until `3113e769` pushed to **master**.
- **Verified after push**: `deploy-info` → `schema_compat: ok`, commit `3113e769`; `/country/id=16` → **404** (not 500); `/ready` still **503** (`generate_province_revenue` stale >2h) — restart **celery-worker** + **beat** on Railway.
- Boot now runs `apply_nextjs_compat_views.py`; provinces view exposes both `userId` and `userid`.

---

### Session: 2026-05-22 (continued)

**Task**: Security fixes + merge to master (PR #42)

**What Was Done**:
- Added `_require_coalition_member()` in `coalitions.py` and guarded `withdraw_from_bank`, `accept_bank_request`, `delete_coalition`, `update_col_info`, `adding`, `removing_requests` (coalition IDOR)
- Province `build_structure_action` ownership check (matches quick-build API)
- Hardened `/_admin/trigger_tasks`, `/_admin/ai_logs`, `/_admin/ai_agent` in `app.py` (ADMIN_DIAG_SECRET only; dual auth for ai_agent)
- Added `tests/test_coalition_membership_guard.py`
- Merged PR #42 into `master` (schema compat + security)

**What To Watch**:
- Ops using `trigger_tasks` must set `ADMIN_DIAG_SECRET` and send `X-DIAG-SECRET` (no SECRET_KEY fallback)
- `ai_agent` requires both diag secret and `X-AI-AGENT-PASSWORD`

---

### Session: 2026-05-22

**Task**: Fix persistent country page 500 (`/country/id=*`, error_id `3f8dq87yxo9nq51s0ayd-1779438499`)

**What Was Done**:
- Refactored `country()` in `countries.py`: core SQL uses only stable columns; optional `join_number`, `last_active`, demographics, and normalized economy queries each wrapped in try/except with safe defaults
- Fixed provinces query to use `CAST(citycount AS INTEGER)` with fallback when demographic columns are absent
- Wrapped revenue `expenses` query in try/except for missing `revenue` table edge cases
- Gated policies checkbox JS in `templates/country.html` behind `{% if status %}`
- Added `scripts/diagnose_country_page.py` (schema probe + query replay) and `scripts/apply_country_page_migrations.py` (applies 0011–0013)
- Added `tests/test_country_page_route.py` (DB-backed smoke for user 16)

**What To Watch**:
- After deploy: `curl -sI https://affairsandorder.com/country/id=27` should return 200
- Run on Railway when `DATABASE_PUBLIC_URL` is set: `python3 scripts/apply_country_page_migrations.py` then `python3 scripts/assign_join_ranks.py` for full join_number display

**Commits**: `113e9eb1` (merge hardened country route), `ef59552e` (DB rollback after optional query failures)

**Verified**: Production `curl -sI /country/id=27` and `/country/id=16` return HTTP 200 after deploy.

**Follow-up (same day)**: Global Affairs menu items (`/countries`, `/coalitions`, `/my_coalition`, `/establish_coalition`) returned 500 for logged-in users — same missing-column pattern (`join_number`, `flag_data`, `tax_rate`, `last_active`, `citycount`). Hardened `countries()`, `coalitions()`, `coalition()` with SQL fallbacks and `rollback_db_cursor()` in `database.py`. Commit `5d65e7d1` on master.

---

### Session: 2026-05-21

**Task**: Fix widespread 500 errors across the site (user report + error_id `km6f39sn3ymh13igdxmr-1779394214`)

**What Was Done**:
- Fixed **swapped `error()` arguments** in `province.py` (3 sites) and `military.py` (1 site) — validation failures were using a string as HTTP status, triggering the global 500 handler instead of 400
- Fixed broken Jinja in `templates/province.html` line 1348 (silos `prores` line missing `}}`)
- Added signup password/confirmation null guards before `.encode()` in `signup.py`
- Hardened `fetchone()[0]` access in `province.py`, `countries.py`, `market.py`, `wars/routes.py`, `coalitions.py`
- Wrapped coalition bank `int(resource)` parsing in try/except
- Added `tests/test_error_handler_status.py` regression tests (error status order, template compile, signup encode)
- Added `.github/workflows/ci.yml` with offline-capable checks; deprecated dummy CI bypass workflow

**Commits**: `64106825`, follow-up hardening on same branch

**Follow-up (same session)**:
- Additional `fetchone()` guards in wars, signup, market, countries, intelligence, admin_tools
- Safe `request.form.get("description")` in countries `update_info`
- `wars/service.py` guard for missing war rows in `update_supply`
- CI script `scripts/check_error_call_order.py` to prevent swapped `error()` regressions
- Removed deprecated `tasks_revenue_optimized.py` (legacy proInfra/resources SQL)
- Fixed unused `CoalitionQueries` in `database.py` to use `coalitions_legacy` schema

**What To Watch**:
- Province/military buy/sell validation should return 400 pages, not global 500 with `error_code`
- Production smoke on test account 16 after deploy (province page, market, wars)

**Next Steps**:
- Monitor Railway logs for `[ERROR! ^^^]` after deploy
- Run DB-backed integration tests in CI when Postgres service is available

---

### Session: 2026-03-04

**Task**: Master Game Economy & Architecture Audit - comprehensive documentation of all economic systems

**What Was Done**:
- Created `scripts/master_economy_audit.py` - comprehensive script extracting ALL economic constants from codebase
- Generated `MASTER_ECONOMY_AUDIT.txt` - complete documentation covering:
  - **Global Economy**: Tax generation (0.025 base, 1.5x with CG), population growth (4% happiness bonus, -2% pollution penalty), province/land/city acquisition costs (8M*1.16^n scaling for provinces, linear for land/cities)
  - **Demographics**: Aging rates (0.2%/0.1%/0.5% per tick), per-capita consumption (working/children/elderly ratios), distribution capacity (50k per building)
  - **Complete Building Catalog**: All 30+ buildings with build costs, gold upkeep, production, consumption, employment matrices, and effects - organized by category (Power, Retail, Public Works, Military, Resource Extraction, Processing)
  - **Debuffs & Crisis Systems**: Unemployment (>30% = -10 happiness), Pension Crisis (>40% elderly = -5k gold), Chernobyl efficiency floor (20% minimum production)
  - **Feature Flags**: All Phase 2/3 systems (ENABLED)
- Commit: `eb9ec317` - pushed to master

**What To Watch**:
- Use this audit report as reference when balancing game economy
- Update the report when new buildings/systems are added
- Consider splitting catalog into separate balance sheets per game phase

**Next Steps**:
- Monitor player feedback on Phase 2/3 balance after systems have been live for 24-48 hours
- Consider adding unit costs and military balance to a separate audit report
- Future: create web UI to visualize economic flows and production chains

---

### Session: 2026-02-06

**Task**: Game unplayably slow - find and fix performance issues

**Root Causes Found**:
1. **Missing database index on `upgrades.user_id`**: 96,000 sequential scans with only 296 index scans - every query on upgrades was doing a full table scan
2. **Task overlap causing deadlocks**: Background tasks (revenue, population) could run simultaneously and lock each other
3. **Redundant database connection** in `country()` - `rations_needed()` opened its own connection when data was already available

**What Was Done**:
- Added missing index: `CREATE INDEX idx_upgrades_user_id ON upgrades(user_id)` - directly on production
- Added missing index: `CREATE INDEX idx_news_destination_id ON news(destination_id)`
- Ran `ANALYZE` on key tables (policies, upgrades, provinces, proinfra, stats, resources, military, users) to update query planner
- Fixed `countries.py` to calculate rations_need from already-fetched provinces data instead of calling `rations_needed()`
- Added `FOR UPDATE` row locking in task_runs table to serialize task executions
- Improved resource delta batching in `generate_province_revenue()` using `execute_batch()`
- Commit: `4f0de6ad` - pushed to master

**What To Watch**:
- Monitor Railway logs for any deadlock errors after deploy
- Background tasks now use row-level locking (`FOR UPDATE`) - shouldn't overlap
- The ~2 second latency seen in local testing is network latency to Railway DB (normal for remote connections)

**Performance Verification**:
- Seq scans on upgrades table should now use index (verify via `pg_stat_user_tables` after some traffic)
- Caching is working correctly (revenue cached calls: 0.0ms)

**Next Steps**:
- Consider adding `@cache_response` decorator to more routes if slowness persists
- The market page doesn't have caching - could add if it's slow
- Monitor for any remaining N+1 query patterns in logs

---

### Session: 2026-02-02

**Task**: Fix province page 500 error for all players

**What Was Done**:
- Fixed corrupted Jinja2 template in `templates/province.html` (lines 735-739)
  - Gas stations section had broken conditional with mismatched parens
  - Orphaned code fragments from bad merge/edit
- Added null/empty location fallback in `province.py` line 87
- Commit: `a124a0c4` - pushed to master

**What To Watch**:
- Other template sections might have similar corruption (search for `| prores` usages)
- Users with empty string locations in `stats` table (4 found: ft_user, integ_a, integ_b, v)
- Orphaned provinces exist (provinces whose users were deleted)

**Database Findings**:
- 86 users have NULL/empty locations in stats table
- Some test accounts have orphaned data
- proInfra and resources are properly linked for all active users

**Next Steps**:
- Consider cleaning up orphaned province data
- Audit other templates for similar syntax issues
- Add template syntax validation to CI/CD

---

### Session: 2026-02-09

**Task**: Coalition bank withdraw request failure (500) when new members request withdraw + leader panel non-responsiveness

**What Was Done**:
- Fixed incorrect error handling that caused a 500: replaced `redirect(400, ...)` with `error(400, ...)` in `deposit_into_bank()` and `request_from_bank()` to return proper 400 responses for non-members
- Hardened `request_from_bank()` DB INSERT with try/except, logging and a friendly 500 error message on insert failure
- Added `tests/test_coalitions_bank_flow.py` which exercises: create leader, establish coalition, create member, submit bank request, leader accepts, and cleanup
- Commits made locally: `7443c66d` (use error() fix), `8bd353f6` (DB insert error handling) and subsequent test/workflow fixes were committed and pushed (`82e8a1c0`, `f81a4db9`, `6fbc96e6`).
- Added an integration-smoke workflow modification to initialize the DB and run the coalition bank test (`.github/workflows/integration-smoke.yml`) — commit `2f3a413b` (pushed). Integration smoke and CI runs for this commit completed successfully.

**What To Watch**:
- Verify in production after deployment that the leader panel shows bank requests created by new members and that acceptance removes the requests correctly
- Watch logs for any `colBanksRequests insert failed` warnings
- Monitor integration smoke workflow for flakiness and DB init timing

**Next Steps**:
- Monitor CI/Integration and production for any regressions from this change
- Added a scheduled daily smoke job (`.github/workflows/smoke-daily.yml`, commit `70ddd666`) that runs `tests/test_statistics_components.py` to detect regressions early
- Optionally add a UI-level E2E test to validate the leader accept flow from a browser automation perspective

---

**Task**: Market statistics missing components (UI showed no market stats for components)

**What Was Done**:
- Added `components` to the `resources` list in `statistics.py` so market statistics include components
- Updated `templates/statistics.html` to show Components rows in Average/Highest/Lowest tables
- Added integration test `tests/test_statistics_components.py` which inserts a components offer using the designated test account (id 16), visits `/statistics`, and asserts the Components row and price appear; the test logs in the client via session and cleans up the offer afterwards
- Commits: `7b0f5711` (fix + test added), `e757cea8` (login fixture adjustment in the test)
- Updated `.github/workflows/integration-smoke.yml` to include `tests/test_statistics_components.py` (commit `9dc55699`) and pushed the change
- Integration smoke run for commit `9dc55699` completed successfully (run id: `21847874476`)
- Verified the new test passes locally and pushed the commits; CI ran and reported success

**What To Watch**:
- Ensure the integration-smoke workflow includes tests that surface market statistics regressions (add if missing)
- Monitor the statistics page in production for expected Components averages once offers exist

**Next Steps**:
- Monitor CI runs and production logs for any regressions related to market statistics
- Consider adding a smoke test that inserts a market offer for an under-represented resource to ensure visibility

### Session: 2026-02-10

**Task**: Reproduce and fix "pollution stuck/fluctuating" (player report: nation 4760)

**What Was Done**:
- Fixed an upward-biased rounding bug in `tasks.py` that used `math.ceil()` for building effects and could cause oscillation. Replaced with `int(round(...))` to avoid an upward bias. (File: `tasks.py`)
- Added lightweight telemetry in `generate_province_revenue()` to emit a task metric `province_pollution_delta` when a province's pollution changes by >= 6 percentage points. This is best-effort and non-blocking. (File: `tasks.py`)
- Added a deterministic regression test `tests/test_pollution_stability.py` that uses the designated test account (id 16), sets up a high-pollution province with both pollution sources and sinks, runs `generate_province_revenue()` multiple times, asserts stability, and restores original state. (File: `tests/test_pollution_stability.py`)
- Added a sandbox repro script `scripts/repro_pollution_4760.py` that copies provinces from nation `4760` into the designated test account, runs the revenue task iteratively, records pollution timelines, and cleans up/ restores original state. This was run against production-like data and **left no trace**. (File: `scripts/repro_pollution_4760.py`)
- Verified locally: the regression test passes and the sandbox repro shows provinces that previously oscillated (or were stuck near 98) are now stable (no wild oscillation). Some provinces remain high (98/100) when no sinks exist (expected behavior).

**Commits**:
- `5701b04c` - "repro(pollution): add sandbox repro for nation 4760; rounding fix; telemetry for large pollution deltas"

**What To Watch**:
- Monitor `province_pollution_delta` metrics in task metrics DB and Prometheus (if available) for repeated large deltas that indicate instability.
- Watch CI for the new test; it should pass on all runners. If the test fails in CI due to DB timing, adjust task_runs preconditions in tests.

**Next Steps**:
- If production reports of oscillation continue, investigate the specific province/proInfra mix and consider adding targeted fixes (e.g., making pollution reductions more robust when near-clamped values exist).
- Consider adding an alert rule to surface provinces that toggle > N times in M runs.

---

---

### Session: 2026-02-10 (continued)

**Task**: Fix province page 500 errors and Celery background task crashes caused by queries to deleted legacy tables

**What Was Done**:
- Migrated all `proInfra` table queries to normalized `user_buildings + building_dictionary` schema
- Migrated all `resources` table queries to normalized `user_economy + resource_dictionary` schema
- Fixed 9 functions in `tasks.py` covering all core background economy tasks:
  - `rations_distribution_capacity()` - building counts for rations distribution
  - `energy_info()` - province energy production/consumption
  - `food_stats()` - rations availability checks
  - `calc_ti()` - consumer goods for tax income calculation
  - `tax_income()` - consumer goods batch preload and deduction
  - `population_growth()` - rations consumption and row existence
  - `generate_province_revenue()` - most complex: rewrote building/resource preload from column-based to name-based dictionaries, batch resource upserts with resource_id mapping
  - `war_reparation_tax()` - resource looting queries for war reparations
  - `backfill_missing_resources()` - utility to ensure all users have all resource_id rows
- Fixed 3 locations in `province.py`:
  - `create_province()` - removed proInfra INSERT (no longer needed)
  - `get_free_slots()` - city/land slot queries now use user_buildings
  - `province_sell_buy()` resource_stuff() - buy/sell building resource deductions now use user_economy with resource_id lookups
- Fixed scope bug in `task_global_tick()` - moved `validation_start` before conditional to prevent "referenced before assignment" error
- Commit: `da07e06b` - "fix: migrate province routes and celery tasks to normalized schema" - pushed to master

**What To Watch**:
- Monitor Railway logs for any "relation 'proinfra' does not exist" or "column does not exist in resources" errors - should be zero now
- Watch Celery worker logs for successful execution of hourly tasks (tax_income, population_growth, generate_province_revenue)
- Check province management page loads without 500 errors
- Verify building buy/sell operations work correctly (resource deductions/additions)
- War reparations should work correctly when wars end

**Technical Details**:
- Query pattern changed from `SELECT {column} FROM resources` to `SELECT quantity FROM user_economy JOIN resource_dictionary WHERE name = %s`
- Building access changed from `SELECT {building_col} FROM proInfra` to `SELECT quantity FROM user_buildings JOIN building_dictionary WHERE name = %s`
- Batch operations now preload all buildings/resources for all users in chunk, map to dicts, then process in loop
- Resource updates changed from dynamic column-based UPDATE to batch upserts: `INSERT INTO user_economy (user_id, resource_id, quantity) VALUES ... ON CONFLICT DO UPDATE`

**Next Steps**:
- Monitor production for 24-48 hours to ensure all background tasks execute successfully
- If any legacy table references appear in logs, investigate and fix immediately
- Test files in `tests/` directory may reference legacy tables - update if tests fail
- Scripts in `scripts/` directory reference legacy tables but are not on critical path (update as needed)

---

### Session: 2026-03-04 (continued)

**Task**: Fix 4 critical production bugs — attack 500, account 500s, market connection leak, electricity soft-lock

**What Was Done**:

1. **Attack route 500 (units.py)**:
   - Root cause: `Units.rebuild_from_dict()` stored `_unusable_units_cache` in `__dict__` → Flask session. On rebuild, `cls(**dic)` received unknown kwarg → TypeError.
   - Fix: Filter out private attributes (`k.startswith('_')`) before passing to `__init__`.

2. **Account route 500s (countries.py, change.py)**:
   - `delete_own_account()`: `DELETE FROM offers WHERE userid=...` but column is `user_id` → crash.
   - `delete_own_account()`: Missing cleanup of `user_tech`, `policies`, `news` → orphaned data.
   - `change()`: `request.form.get("current_password")` can be `None`, `.encode()` on None → AttributeError.
   - Fix: Corrected column name, added missing DELETEs, null-safe password handling.

3. **Market connection leak (market.py)**:
   - `give_resource()` finally block created a NEW `get_db_connection()` context manager and called `__exit__` on it instead of closing the original `conn`.
   - Fix: Replaced with `conn.close()`.

4. **Electricity soft-lock (variables.py)**:
   - Coal burners required aluminium, oil burners required aluminium, solar fields required steel — but these processing outputs require power plants (circular dependency).
   - Fix: Coal burners → lumber (40k), Oil burners → lumber (60k) + iron (20k), Solar fields → copper (40k) + bauxite (30k). All Tier 1 resources mined without power.

**Commit**: `e24a86d3` — pushed to master

**What To Watch**:
- Verify attack flow works end-to-end: warchoose → waramount → warResult
- Verify delete account, change name, change email all work
- Monitor for connection pool exhaustion (was leaking before fix)
- Verify new players can build coal/oil burners and solar fields with only Tier 1 resources

**Next Steps**:
- Monitor Sentry for any remaining 500 errors on war/account/market routes
- Legacy table references still exist in test files and scripts — update when those are exercised
- Consider adding integration tests for the attack flow and account deletion
---

### Session: 2026-03-06 (continued from Phase 17 economy audit)

**Task**: Player "The_Kaiser" (KR coalition) reports all resources are frozen after commit `110f210d` (5-bug fix deploy). Investigate why resources aren't changing.

**What Was Done**:

**Stage 1: Root Cause Discovery**
- Agent identified that Celery beat process died during the 5-bug fix deploy. The beat script tried to acquire a Redis lock held by the old process, failed (TTL not expired), and exited with `sys.exit(0)`. Railway's `restartPolicyType: ON_FAILURE` doesn't restart processes that exit with code 0 → beat stayed dead for 4+ hours.
- Evidence: task_runs table showed all tasks stopped between 17:00-17:45 UTC (when deploy occurred). game_tick_logs showed old code still running (tick_id 293 had `production_entries: 51`, meaning `BUILDING_PRODUCTION_RESOURCE_MAP` wasn't empty yet).

**Stage 2: Beat Retry Logic Fix**
- Fixed `/scripts/run_beat_if_leader.py`:
  - Added retry loop with backoff: retries acquiring Redis lock for up to `LOCK_TTL * 2` seconds (120s) with 5-second intervals.
  - Changed failure exit from `sys.exit(0)` to `sys.exit(1)` so Railway restarts on failure.
  - Added lock refresh loop while beat runs to keep it alive.

**Stage 3: Additional Bugs Fixed During Investigation**
- **Dict mutation bug in tasks.py** (lines ~2161, 2313, 2320): `plus`, `eff`, `minus`, `effminus` dicts from `variables.NEW_INFRA` were being mutated in-place (e.g., `plus["energy"] += 6`, `eff["happiness"] *= 1.3`). Values would compound across building loop iterations and task runs, eventually producing astronomically wrong values. Fixed by using `dict()` copies before modifications.
- **tax_income cg_map key bug** (line ~855): Query returns `user_id` column but code used `row.get("id")` → all CG values mapped to `cg_map[None]`. Tax income CG consumption was completely broken. Fixed to use `row.get("user_id")`.
- **conn.rollback() scope bug** (line ~2484): Per-building exception handler called `conn.rollback()` which undid earlier DB writes (e.g., user_economy row ensures). Building loop only modifies in-memory dicts, so rollback was unnecessary and harmful. Removed and replaced with print logging.
- **upgrades.py Blueprint import error** (new in this session): When tasks.py imported `get_upgrades` from upgrades.py, the entire module loaded including `bp = Blueprint(...)`. In Celery worker context (no Flask app), this could fail. Fixed by wrapping `bp` creation in try/except and checking for None in app.py.

**Stage 4: Deployment & Verification**
- Commits:
  - `3f16b2fa` — beat retry, dict mutation, cg_map, rollback fixes
  - `65c5137e` — added `/_admin/trigger_tasks` endpoint for manual task triggering
  - `048db660` — SECRET_KEY fallback for auth
  - `0b96f0c5` — DISCORD_CLIENT_SECRET fallback for auth
  - `0fc1a5b8` — upgrades.py Blueprint import fix
- After ~20 minutes, `population_growth` and `execute_trade_agreements` both ran at 21:45 UTC ✅
- At 22:00 UTC: `tax_income`, `global_tick` (*/10), `execute_trade_agreements` (*/15) all fired ✅
- At 22:10, 22:15, 22:20 UTC: background tasks continued firing on schedule ✅
- At 22:25 UTC: `generate_province_revenue` fired for the first time since 17:33 ✅
- Verified new code running: tick 294 showed 0 production entries (double-production bug from commit `110f210d` confirmed fixed), consumption entries working.
- **Issue**: `generate_province_revenue` ran but resources for user 781 didn't change. No resource updates in DB after 22:25 run. Investigated: resources preloaded correctly, buildings mapped correctly, energy check logic correct, but likely import failure when loading `get_upgrades` prevented task completion.

**Stage 5: Import Error Fix & Deployment**
- Root cause: `tasks.py` line 1947 imports `from upgrades import get_upgrades as _get_upgrades`. In Celery worker, `upgrades.py` module-level code runs, including `from flask import Blueprint`. In some environments or after certain Flask versions, importing Flask Blueprint outside app context can fail.
- Fixed by wrapping `bp = Blueprint(...)` in try/except and checking `if upgrades.bp:` in app.py before registering.
- Commit: `0fc1a5b8` — pushed to master
- Deploy should resolve the issue and allow `generate_province_revenue` to complete successfully on the next run at 23:25 UTC.

**What To Watch**:
- At 23:25 UTC: verify `generate_province_revenue` runs and resources actually increase for players
- Monitor Celery worker logs for any import errors related to upgrades or Flask
- If resources still don't change, investigate whether task error handling is suppressing exceptions (check task_runs.error_log, if it exists, or Sentry)
- Verify coalition bank requests and market offers still function (also use upgrades module indirectly)

**Next Steps**:
- Wait for 23:25 UTC to verify generate_province_revenue completes and updates resources
- If resources change ✅, inform user that issue is resolved and system is producing again
- If resources still don't change ❌, investigate whether:
  1. Task is crashing but not logging (add exception handler logging)
  2. Resource updates aren't committing (check transaction/commit logic)
  3. A different import error is blocking task execution
- Consider adding telemetry to generate_province_revenue to track: provinces processed, resource deltas applied, batch insert counts
- Document the "beat process dies on deploy with exit code 0" issue and solution for future reference

```

---

### Session: 2026-03-18

**Task**: 50M gold giveaway delivery to LD + fix revenue display bug

**What Was Done**:

1. **50M Gold Giveaway Delivery**:
   - Sent 50,000,000 gold to giveaway winner "Donnerkrawall" (Discord) / **ld_real** (in-game, user ID 69697533)
   - Used `admin_add_resource()` to add gold — updated `stats.gold` from 40,010,376 → 90,010,376
   - Verified delivery via DB query

2. **Revenue Display Bug Fix (countries.py + country.html)**:
   - **Bug 1 — Coalition tax not shown**: `get_revenue()` did not account for coalition tax. LD is in "Leviathan" coalition (colid 86) with 20% tax rate. Display showed ~17.6M net but actual income after tax was ~13.9M (matching LD's reported "12m"). Fixed by adding coalition tax lookup from `coalitions_legacy + colNames` tables and deducting from displayed net money. Added `revenue["coalition_tax"]` field.
   - **Bug 2 — CG formula mismatch**: Display used legacy `pop/80000` formula while actual `tax_income()` task uses demographic-based consumption (`FEATURE_DEMOGRAPHIC_CONSUMPTION`). Fixed by adding demographic branch to `get_revenue()` with distribution capacity check, falling back to legacy formula when feature flag is off.
   - **Template update**: Added coalition tax line item in red on country page (`country.html`) after "Monetary net" row.

3. **Discord Response**:
   - Posted message in #50m-giveaway channel explaining the fix to LD and confirming giveaway delivery

**Commits**:
- `25a4211f` — "fix: revenue display now accounts for coalition tax & demographic CG consumption" — pushed to master

**Files Changed**:
- `countries.py` — `get_revenue()` function: added coalition tax deduction, demographic CG formula
- `templates/country.html` — added coalition tax display row

**What To Watch**:
- Verify LD's country page now shows ~13.9M net (down from ~17.6M) after deploy
- Other players in coalitions with tax rates should also now see accurate net revenue
- The demographic CG formula and legacy formula converge for most players but could diverge for edge cases with unusual demographic distributions

**Next Steps**:
- Monitor player feedback on revenue accuracy
- Consider adding coalition tax rate to the revenue breakdown tooltip or info panel
- Legacy table references still exist in test files and scripts — update when exercised

### Session: 2026-09-27 — Grouped navigation (hubs + section tabs)

**What was done**:
- Navbar dropdowns listed every page flat (10 under Internal Affairs, 9 under Global Affairs). Pages are now grouped into 6 hubs, and each hub's pages share a tab strip above the page content, the same idea as the country page's View/Revenue/News/Edit tabs:
  - Internal Affairs: **Nation** (Overview · Provinces · Projects), **Economy** (Market · Trade Agreements · Loans · Bonds · Currency Unions), **Military** (Forces · Wars · Bounties)
  - Global Affairs: **Coalitions** (My Coalition · All Coalitions · Establish), **Nations** (Countries · Rankings), **Diplomacy** (Treaties · Assembly · World Affairs)
  - Other: unchanged.
- `app_core/navigation.py` (new) is the single source of truth: `NAV_SECTIONS` plus `build_nav(path, user_id, coalition_id)`. It drives the desktop dropdowns, the mobile hamburger menu, the tab strip and the bottom-nav active state. Add or move pages there, not in `layout.html`.
- `templates/partials/section_tabs.html` (new) is included in `layout.html` just before `{% block body %}`. It only renders for logged-in users on a page that belongs to a hub with more than one page.
- `app.py`: added an `inject_site_nav` context processor (in-memory only, no DB). `inject_layout_context` rebuilds the nav with the viewer's coalition id, because `/my_coalition` redirects to `/coalition/<id>` and that page should keep the "My Coalition" tab lit.
- CSS in `static/css/game-layout.css` (bundled): the strip is one horizontally scrolling row of 44px pills with an edge fade on phones, and wraps inline with the hub title from 768px up.

**What to watch**:
- Rendered through the real `layout.html` with a stubbed session, and screenshotted at 390px (dark and light) and 1440px, including the hamburger and the dropdown hover. Not yet checked on live pages whose `.templatediv` is not the first child of the body block. Spacing there may need a per-page tweak.
- `/country/id=<own id>` goes to the Nation hub; other players' country pages go to Nations → Countries.
- `tests/test_layout_navbar_structure.py` fails both before and after this change. It slices hard-coded line ranges out of `layout.html`, and those ranges no longer contain complete markup.

**Next steps**:
- `templates/partials/quick_nav.html` (logged-in home grid) still lists pages individually. It could be regrouped by hub if players want that.

### Session: 2026-09-28 — Rankings cleanup + one-frame-per-panel on v2 pages

**Root cause**: v2 (glass) pages stacked up to four frames around one table. The page wrapper `.templatediv` kept its border and shadow after its fill was made transparent, which left a ghost outline around the page. Inside that sat the `.game-glass` panel. Its title was a full `.templatecontentheaderleft` bar, and below it came `.templateoutertablediv` (90% wide, inset) and then `.templatetable` (90% again, with its own glass fill, border and shadow). On a 390px phone that left ~250px for the table, so the value column was clipped. The generic ≤768px "scroll table + sticky first column" mode also painted an opaque block down the rank column.

**What was done**:
- `static/css/game-glass.css` (shared, v2 pages only): removed the ghost `.templatediv` frame. Inside a `.game-glass` panel, the table wrapper and table are now full-width and frameless. The panel's own title (first-child `h2.templatecontentheaderleft`) is now a compact left-aligned label with an accent icon. `.game-panel` padding shrinks on phones (≤620px).
- `templates/macros/game_ui.html`: `game_glass_panel` uses the `.game-panel` class instead of inline padding, so the mobile padding rule can apply.
- `templates/rankings_v2.html`: the four copy-pasted tables are now one local `leaderboard()` macro. It adds a real `<thead>` and puts the flag and name in one flex link, so long names and equipped titles wrap next to the flag instead of under it. The top 3 ranks are shown in `--gold`.
- `static/css/game-experience.css`: rebuilt the rankings table rules. The page opts out of the generic mobile scroll-table mode and the 480px `img { height:auto !important }` hack. It uses a fixed layout (narrow rank, flexible name, right-aligned value). The two leaderboards stack below 1100px.
- Verified by rendering the real `layout.html` + `rankings_v2.html` with mock data and screenshotting at 390px (dark and light) and 1280px.

- Follow-up after a full sweep of all 33 `*_v2.html` pages. Each was rendered through the real layout with placeholder data, before (HEAD~1) and after, at 390px dark/light and 1280px, then pixel-diffed and reviewed side by side:
  - Frameless tables now apply only to a panel's *direct* table. The first version also stripped the Country page's General card, leaving it mismatched with the Demographics card beside it.
  - On phones, the sticky first column of v2 tables uses frosted glass instead of opaque `--tableOne`/`--tableTwo`, so there's no dark slab down the table.
  - An empty-state row (one colspan cell) is no longer sticky.
  - Header cells stay transparent.

**What to watch**:
- The sweep used placeholder data, so pages with long real content (full coalition member lists, large market tables) weren't seen with real rows.
- Pre-existing and not fixed here: `trade_agreements_v2` renders 413px wide on a 390px phone (horizontal page scroll). The `account_v2` details table scrolls sideways on phones because it has 3 columns of inputs.

**Next steps**:
- Apply the same audit to the other v2 pages with dense tables (market, statistics, coalitions list).

### Session: 2026-09-28 — Trade Agreements page rebuilt to match the v2 pages

**Problem** (reported as "looks very outdated"):
- The page used legacy chrome: `.infodiv` for the form, a `.templatecontentheaderleft` bar per section, and 5-7 column `.templatetable`s.
- An inline `<style>` used tokens that don't exist (`--bg-color`, `--bg-color-alt`, `--font-header`, `--text-muted`) plus hardcoded `#e74c3c`/`#2ecc71`.
- It rendered 413px wide on a 390px phone, so the whole page scrolled sideways.

**What was done**:
- `templates/trade_agreements_v2.html` was rewritten:
  - Hero with subtitle and an "N active" badge.
  - "Waiting for your answer" panel first when there are incoming proposals.
  - "New proposal" form beside "How it works" (two columns from 1000px).
  - One "Your agreements" panel grouped Active / Paused / Sent / Completed. Completed is collapsed in a `<details>`.
  - Each agreement is a card, always from the viewer's side: You give / You get chips with resource icons, compact amounts (`fmt`, full value in `title`), interval, trade count and next run. Actions are `game-btn`s.
  - Form field names, the partner-search JS and all POST routes are unchanged.
- `static/css/game-trade.css` is new and added to `scripts/bundle_game_css.py` FILES. It is mobile-first and uses tokens only. Deal cards are stacked on phones and tablets and become one row from 900px. It overrides the global centred `label` rule for form labels.
- Verified with rendered mock data (every status plus the empty state) at 390px dark/light, 820px and 1280px dark/light. There is no horizontal overflow at any width.

**What to watch**:
- `tests/test_trade_agreement_no_double_execution.py` needs a live DB. It fails the same way with and without this change.
- The legacy `trade_agreements.html` (non-v2) was not touched.

### Session: 2026-09-28 — Military page rebuilt

**Problem** (reported as "in the worst shape of the whole game"):
- `military_v2.html` was 1,170 lines: 16 hand-copied ~50-line unit blocks, several with `<form>` closing outside the div it opened in.
- A ~280-line inline `<style>` fought legacy `.warflexparentcolors`/`.unitimage` rules with `!important`.
- Each unit card was ~1.5 phone screens tall. The photo sat below the buy form, Buy/Sell were stacked full-width, costs were a prose sentence, and there were four levels of heading per unit.
- "You can purchase N more today" was wrong: `compute_display_limits` returns building capacity, not a daily limit.
- The Artillery/Tanks note "cap of 150 troops per Army Base" contradicted the code (200 per base).

**What was done**:
- `templates/military_v2.html` is now data-driven: one `branches` list (key, name, image, description) plus one `unit_card` macro.
  - Tabs keep the ids/onclick names `static/script.js` TAB_GROUPS.military toggles (`#militaryland` / `#land`, …) and now show branch unit totals.
  - Cards: photo strip, name + owned count, ATK/DEF pills, description, cost chips built from `mildict` (the same source the old `milres` filter used, including the Widespread Propaganda 0.65 soldier price), upkeep, and one `Amount | Buy | Sell` row with "Room for N more".
  - Drones/missiles keep their activate form and stockpile count.
- Verified all 17 units render a form with the correct input name and `/military/buy|sell/<unit>` or `/military/activate/<unit>` targets. CSRF comes from `layout.html`'s auto-injection, as before.
- `static/css/game-military.css` is new and added to the bundle. It is mobile-first: 4-up icon tabs and 1 column on phones, 2 columns from 700px, 3 from 1100px.
- Screenshotted at 390px dark/light, 820px and 1280px dark/light with mock data, including switching to the Special tab. Mobile page height went from 3,567px to 2,215px on the Army tab.

**What to watch**:
- `tests/test_military_rebalance.py` / `test_normalized_military.py` need a live DB and fail identically before and after.
- Unit descriptions were tightened (facts unchanged, "figher" typo fixed). The stale 150-per-base note was dropped.
- The legacy `military.html` (non-v2) was not touched.

### Session: 2026-10-03 — Fix treasury draining with false positive Net Monetary Profit

**Problem** (reported by Kurai & luciuskonst in `#bug-reports`):
- Players with empty treasuries or running economic deficits saw positive numbers under "Monetary net" on the country page ("Net Raw") even though their treasury was draining every hour.
- Root causes:
  1. In `countries.py` (`get_revenue`), `revenue["net"]["money"] -= upkeep_op["cost"]` was nested inside the `simulated_funds` check for physical resource production. When treasury was empty or upkeep exceeded tax income, unaffordable buildings skipped deduction, hiding the building upkeep deficit.
  2. Coalition tax was previously deducted from gross tax revenue rather than net profit, eroding operating margins.
  3. The "Net Raw" panel had no stat card for Building Upkeep, leaving players unaware of their total hourly building expenses.

**What was done**:
- `countries.py`: Unconditionally deducted `total_building_upkeep` from `revenue["net"]["money"]` and exposed `building_upkeep` in `filtered_revenue`. Adjusted coalition tax in projection to apply against net taxable profit (`max(0, ti_money - total_building_upkeep)`).
- `app_core/game_ticks/taxes.py`: Aligned alliance tax in hourly tick to deduct percentage from net profit (`max(0, money - upkeep)`), protecting building operating costs.
- `templates/country_v2.html` & `templates/country.html`: Added a dedicated `Building upkeep` stat card under `Net Raw`, styled `Monetary net` with conditional red/green color, and guarded against `-0` in coalition tax display.
- `tests/test_monetary_net_deficit.py`: Added 2 unit regression tests verifying full building upkeep is deducted when treasury is 0 or upkeep exceeds taxes.
- Documented Discord automation rule in `CLAUDE.md`, `GEMINI.md`, and global memory (`user_global.md`, `claude_memory_ano.md`).
- Commits: `f0ef7e03`, `25c3711d`, `ef6d2ca2`.

**What to watch**:
- Physical resource simulation remains strictly gated by `simulated_funds` (idle buildings still do not produce physical resources when broke).

