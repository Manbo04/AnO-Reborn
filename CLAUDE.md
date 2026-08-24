# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This document defines preferences, standards, and context for all AI sessions working on this project. **Read this fully before starting any task.** (Same rules are mirrored for the Gemini CLI in `GEMINI.md`, and for GitHub Copilot in `.github/copilot-instructions.md`.)

---

## 📱 MOBILE-FIRST UI (non-negotiable)

The game UI **must be built mobile-first** — most players are on phones/tablets.
Design and verify every UI change at mobile width FIRST (~390px phone, ~820px
tablet), then enhance for desktop. Do not build desktop-first.

Every mobile bug shipped so far came from ignoring this: signup/biome page
rendered fully unstyled on tablet, desktop side-ad rails leaked full-width onto
touch devices, cramped province building lists, oversized banner/flag images
filling the screen.

- Cap all images (`max-width:100%`, bounded height, `object-fit`) — nothing may
  fill the screen on mobile.
- Desktop-only chrome (side ad rails, wide multi-column layouts) gated behind
  BOTH `min-width` and `pointer:fine`; must never affect mobile flow.
- Overflowing lists scroll, they don't shrink-to-fit (`flex-shrink:0` on rows).
- `.com` serves OAuth signup/login pages, `.org` is primary, both behind
  Cloudflare. CSP must allow BOTH apex domains in script-src/style-src/connect-src
  or `.com` signup pages render unstyled on mobile.
- CSS is bundled: edit `static/css/*.css` then run
  `python3 scripts/bundle_game_css.py`; never hand-edit `style.min.css`.

---

## ⛔ NEVER `railway up` against prod-validator

`prod-validator` is the **production Postgres database** (despite the name), and
it is this project's DEFAULT linked service. On 2026-07-05 a stray `railway up`
deployed the app repo onto it, replacing postgres:17 and taking the whole game
down for ~1 hour (recovered by redeploying the old postgres:17 deployment via
the API; clean shutdown, no data loss). Before ANY `railway up` or `railway
redeploy`, run `railway status` and confirm the linked service is `web` (or
`bot`/`celery-worker`) — never `prod-validator`. Deploys normally happen by
pushing to master, not by `railway up`.

---

## 🔧 Available Tools & Access

The AI has access to:
- **GitHub MCP** - Repository management, PRs, issues, branches
- **Railway** - Production database via `DATABASE_PUBLIC_URL`
- **ano-game MCP** - Direct game database queries (nations, resources, wars, etc.) — served from `mcp-server/` (Node/TypeScript, `pg` driver)
- **Context7 MCP** - Up-to-date library documentation (use `use context7` in prompts)
- **Local terminal** - Full shell access for running scripts, tests, deployments

**Do NOT ask if these are available. They are. Use them.**

---

## ⚠️ Critical Working Preferences

### On Fixing Issues
1. **Fix it completely the first time.** Do not provide partial fixes or "try this and see."
2. **Always test after fixing.** Run the relevant code path, query the database, or use the test client.
3. **Check for cascading breakage.** After any fix, grep/search for related usages that might also be affected.
4. **Never ask "should I continue?"** - Yes, always continue until the fix is verified working.
5. **Deep testing is expected.** Don't stop at surface-level checks.

### On Code Quality
1. **Detailed and properly structured code.** No shortcuts, no "you can add more later."
2. **Follow existing patterns** in the codebase.
3. **Add proper error handling** - never let exceptions bubble up unhandled.
4. **Use type hints** where the codebase uses them.
5. **Comments for non-obvious logic** - especially for database queries and game mechanics.

### On Performance
1. **Never degrade performance.** Any new feature, fix, or change must not increase loading times or server load.
2. **Avoid N+1 queries.** Use JOINs and pre-aggregated subqueries instead of correlated subqueries.
3. **Fix inefficiencies when found.** If you encounter slow code during your work, fix it - don't leave it.
4. **Use database indexes.** Check that queries have appropriate indexes; add them if missing.
5. **Minimize database round-trips.** Batch queries where possible, avoid redundant fetches.
6. **Test performance impact.** For significant changes, verify query plans and execution times.

### On Testing — Single Test Account Discipline
1. **Use a SINGLE designated test account for ALL testing**: `Tester of the Game` (user ID 16, has 2 provinces).
2. **Never create multiple test users** (e.g. `provtest_*`) — this causes database bloat that has degraded query performance before. Every test account left behind is debt that must be paid back immediately.
3. **Never test on real player accounts.**
4. **Record original state BEFORE testing, restore it AFTER** — delete test market offers, reverse resource changes, remove test wars/declarations, undo coalition changes.
5. If a test can't be cleaned up synchronously, run `scripts/cleanup_test_nations.py` to purge orphaned test users before deploying.

### On Communication
1. **Don't ask permission repeatedly.** If a task is given, complete it.
2. **Don't list what you're "about to do"** - just do it.
3. **Be concise.** Skip unnecessary preamble.
4. **Show results, not intentions.**

### Anti-Patterns to Avoid
1. **Don't create summary markdown files** after each task unless explicitly requested.
2. **Don't ask "would you like me to..."** - just do it.
3. **Don't provide code blocks** for the user to copy - use the edit tools.
4. **Don't suggest manual steps** when automation is possible.
5. **Don't leave TODOs in code** without addressing them.

### Quality Checklist (Before Marking Complete)
- [ ] Code runs without errors
- [ ] Tested with real data from production database
- [ ] No regressions in related functionality
- [ ] Follows existing code patterns
- [ ] Committed and pushed (if deployment needed)
- [ ] Session summary added to `docs/SESSION_LOG.md` (root cause, fix, commits, what to watch)

---

## Development Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set DB credentials, SENTRY_DSN, etc.

# Run locally (needs DATABASE_PUBLIC_URL or a local Postgres via .env)
flask run                       # http://127.0.0.1:5000
# or, matching the venv used in past sessions:
./venv310/bin/python -m flask run

# Run tests
pytest                          # offline-capable subset auto-skips legacy-schema tests
pytest tests/test_country_page_route.py           # single file
pytest tests/test_country_page_route.py::test_x   # single test
RUN_LEGACY_SCHEMA_TESTS=1 pytest                  # include legacy proInfra/resources tests (tests/conftest.py)

# Lint / format (also run by pre-commit and CI)
black .
flake8                          # max-line-length=88, see [flake8] in setup.cfg
ruff check .

# CI-equivalent static checks (see .github/workflows/ci.yml)
python scripts/check_error_call_order.py       # helpers.error(code, msg) arg order
python3 scripts/check_template_json_blocks.py  # Jinja JSON.parse safety
python3 scripts/check_legacy_schema_refs.py    # no new proInfra/resources references
python3 scripts/check_csrf_forms.py            # auth forms include CSRF token
python3 scripts/bundle_game_css.py && python3 scripts/check_game_css_bundle.py

# Celery (background jobs — needs Redis)
celery -A tasks worker --loglevel=info
celery -A tasks beat --loglevel=info

# Deploy
git push origin master          # Railway auto-deploys `web`, `bot`, `celery-worker`
```

---

## Architecture

**Flask monolith, mid-migration to a modular layout.** `app.py` is the single
entrypoint: it configures the app, initializes Sentry (if `SENTRY_DSN` set),
and wires up every feature by calling that feature's `register_<name>_routes(app)`
(e.g. `signup.register_signup_routes(app)`, `countries.register_countries_routes(app)`).
To find how a route is wired, grep `app.py` for `register_`.

Two coexisting code layouts:
- **Legacy flat modules at repo root** — `province.py`, `countries.py`, `market.py`, `units.py`,
  `variables.py` (game constants: prices, unit stats, building catalog), etc. Most game logic
  still lives here. `province.py` is the most frequently touched and most bug-prone file.
- **`app_core/`** — newer modular package (`economy/`, `game_engine/`, `game_ticks/`, `coalitions/`,
  `auth/`, `market/`, `military/`, `admin/`, `tutorial/`, `onboarding/`, `world_map/`, `events/`, …).
  New work tends to land here rather than as new root-level files.
- **`repositories/`** — a repository-pattern data-access layer (`user_repository.py`,
  `province_repository.py`, `country_repository.py`) that's gradually wrapping the raw-SQL calls
  used elsewhere.
- **`wars/`** — a self-contained blueprint package (`routes.py` + `service.py` + `data.py`),
  the pattern newer features tend to follow instead of one flat file.

**Data layer is raw SQL over PostgreSQL** via `psycopg2`. `database.py` centralizes connection
pooling, an in-memory query cache (`@cache_response(seconds)`, invalidated via the `_response_cache`
attribute or the `invalidate` helper), and `execute_batch()` for bulk writes. The usual pattern is
`get_db_cursor()` as a context manager (`db.execute(sql, params)`, auto-commits on exit);
`get_db_connection()` when manual transaction control is needed.

Schema note: the DB was migrated off legacy `proInfra`/flat `resources` columns to a normalized
schema — `user_buildings` + `building_dictionary`, and `user_economy` + `resource_dictionary`
(keyed by `resource_id`/name lookups instead of one column per resource). `scripts/check_legacy_schema_refs.py`
in CI blocks new code from reintroducing the old tables; `tests/conftest.py` auto-skips tests still
written against the legacy schema unless `RUN_LEGACY_SCHEMA_TESTS=1`. `SYSTEM_ARCHITECTURE.md`
predates this migration (and pins Flask 1.1.2, while `requirements.txt` is on Flask 2.3.3) — treat it
as historical background, not ground truth; `database.py` and `migrations/` are current.

**Background jobs** run via Celery (`tasks.py` plus `app_core/game_ticks/` — `revenue.py`, `taxes.py`,
`population.py`, `energy.py`, `food.py`, `maintenance.py`, `locks.py`). Redis is the broker/backend.
Celery beat leader election uses a Redis lock (`scripts/run_beat_if_leader.py`); if beat and a worker
disagree about who holds the lock, background economy ticks silently stop.

**Separate services in this same repo, deployed independently on Railway:**
- `web` — the Flask app above.
- `discord_bot/` — a standalone Discord bot service (`discord.py`), started via `python -m discord_bot.main`,
  talking to `web` through `bot_api.py` (`BOT_API_SECRET`-authenticated endpoints: `/api/bot/register`,
  `/me`, `/nation`, `/wars`, `/resources`).
- `mcp-server/` — the "ano-game MCP" Node/TypeScript server referenced above, queries the game DB directly via `pg`.
- `celery-worker` / beat — the background task runners.

**Auth**: session-based (`session['user_id']`), `@login_required` decorator, Discord OAuth2
(`login.py`, `DISCORD_CLIENT_SECRET`) plus normal email/password. `@check_required` guards
multi-step flows that depend on session state (e.g. `session['enemy_id']` during a war declaration).
Flask-WTF CSRF is required on auth forms (`scripts/check_csrf_forms.py` enforces this in CI).

**Errors**: use `helpers.error(code, message)`, not `abort()` — it renders `error.html` with the
correct HTTP status. A very common regression in this codebase is swapping the argument order
(`error(message, code)`), which routes into the generic 500 handler instead of returning the
intended 4xx; `scripts/check_error_call_order.py` runs in CI to catch this.

**Templates/static**: Jinja2 under `templates/`, most routes render directly. CSS is authored in
`static/css/*.css` and bundled/minified by `scripts/bundle_game_css.py` into `static/style.min.css`
— never hand-edit the minified file (see mobile-first section above for why bundling matters for CSP).

**Two apex domains behind Cloudflare**: `.com` serves OAuth signup/login, `.org` is primary — see
the mobile-first section for the CSP implications.

**Docs worth knowing about**: `docs/` has deploy/runbook/schema-decision docs (e.g.
`CELERY_BEAT_RUNBOOK.md`, `DATABASE_SCHEMA_DECISION.md`, `STYLE_BIBLE.md`); root-level `.md` files
like `PERFORMANCE_OPTIMIZATIONS.md` and `RESTRUCTURE_PLAN.md` document past investigations and are
often the fastest way to learn *why* something is structured a certain way. `docs/SESSION_LOG.md`
has the full chronological history of past debugging/feature sessions on this repo.

---

## Session Handoff Protocol

At the end of each session or major task, append an entry to `docs/SESSION_LOG.md` documenting:

- **What was done** — files changed and why, commit hashes.
- **What to watch** — areas needing follow-up, code that wasn't fully tested, edge cases missed.
- **Next steps** — pending improvements, technical debt, unaddressed user reports.
