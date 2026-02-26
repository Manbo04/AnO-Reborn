# AI Coding Assistant Instructions for Affairs & Order

This repository powers the Affairs & Order game. The following notes are **critical** for any AI agent to be immediately productive. Read fully and refer back often when working here.

---

## 🧱 High‑Level Architecture

- **Flask monolith** with a single `app.py` entrypoint.  Routes are scattered across many feature modules; each exposes a `register_<feature>_routes(app)` function which is called from `app.py` during startup.  Look at `app.py` to see the registration order and global configuration.

- **Data layer** is raw SQL over PostgreSQL.  `database.py` centralises connection pooling, helpers and an in‑memory query cache.  Most modules call `get_db_cursor()` as a context manager and execute `db.execute(sql, params)`; writes are auto‑committed on context exit.

- **Background jobs** live in `tasks.py` and are executed with Celery.  Redis (or RabbitMQ in some docs) is the broker/ backend.  Periodic jobs are registered in the same file.

- **Constants and game rules** are in `variables.py` (e.g. prices, military definitions).  Many other modules import from there.

- **Helpers** (decorators, error template, caching utilities) live in `helpers.py`.  Common response caching is implemented with `@cache_response` from `database.py`.

- **Templates & static assets** are under `templates/` and `static/`.  Jinja2 is used; most route handlers render templates directly.

---

## 📁 Key Files & Directories

| Path | Purpose |
|------|---------|
| `app.py` | Main flask app, configuration, route registration, middleware hooks. |
| `database.py` | DB connection helpers, caching, `cache_response` decorator. |
| `helpers.py` | `error()`, `login_required`, `check_required`, flag/image utilities, audit metrics. |
| `tasks.py` | Celery configuration and all background tasks (revenue, wars, etc.). |
| `province.py` | Province‑centric logic – frequently modified and bug‑prone. |
| `variables.py` | Game constants (unit prices, resource names). |
| `tests/` | Pytest tests; use the test account patterns described below. |
| `migrations/` | DB migration scripts (rarely touched by AI). |
| `docs/` | Project-specific documentation (useful for deep dives). |


---

## ✅ Typical Developer Workflows

1. **Install & start**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env         # set DB credentials, SENTRY_DSN, etc.
   flask run                    # service available at http://127.0.0.1:5000
   ```

2. **Run tests**:
   ```bash
   flask run    # app must be running for most tests
   pytest      # executes `tests/`; uses test DB defined in .env
   ```
   - **Important**: tests must clean up after themselves. See `CLAUDE.md` for the tester‑account rules.

3. **Celery** (background worker):
   ```bash
   celery -A tasks worker --loglevel=info   # as defined in Procfile
   celery -A tasks beat --loglevel=info     # if running periodic jobs locally
   ```
   - Redis URL is configured via `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`.
   - `docker-compose.yml` has a `celery-worker` service used by CI and deployments.

4. **Database**:
   - `get_db_cursor()` is the usual pattern; `get_db_connection()` when manual commit or transaction control is needed.
   - Use `execute_batch()` (imported in `database.py`) for bulk updates.
   - Use `query_cache` (also in `database.py`) for frequently accessed values (flags, province counts, etc.)
   - When adding a new table or index, update migrations accordingly.

5. **Deployment & others**:
   - Environment variables drive configuration (`DATABASE_URL`, `DISCORD_CLIENT_SECRET`, `SENTRY_DSN`, `ENVIRONMENT`, `RAILWAY_ENVIRONMENT_NAME`, etc.).  `.env.example` lists the common ones.
   - Railway is used for production; push to `master` triggers deploy.  CI workflows are under `.github/workflows` (currently no `.github` directory, see examples in repo).
   - Sentry initialized in `app.py` if `SENTRY_DSN` present.
   - Discord OAuth used for login (`login.py` handles it).  Look for `DISCORD_CLIENT_SECRET` and the `login_required` decorator.

---

## 🧭 Project‑Specific Patterns & Conventions

* **Route registration**: always call `register_<name>_routes(app)` from `app.py`.  This is how new features are wired.
* **SQL style**: prefer multi‑line strings with `(%s)` placeholders, pass parameters as tuples.  Avoid SQL injection by never formatting user input directly.
* **Error responses**: use `helpers.error(code, message)` instead of `abort()`; it returns the `error.html` template and correct HTTP status.  Failing to use it often causes 500s in tests.
* **Login enforcement**: decorate protected views with `@login_required`; session uses `session['user_id']`.
* **Session checks for multi‑step flows**: use `@check_required` to redirect if `session['enemy_id']` is missing (common in war flows).
* **Caching page responses**: apply `@database.cache_response(seconds)` on expensive read‑only views.  Invalidate caches with `invalidate` helper or by referencing `_response_cache` attribute.
* **Performance awareness**: avoid N+1 queries; check how similar pages (e.g. `market.py`, `countries.py`) batch data.  Query plans should be inspected when in doubt.
* **Test account**: always use **user ID 16, name "Tester of the Game"** in tests.  This account has exactly two provinces.  Reset state when done (delete offers, wars, resource changes, etc.).
* **SQL caching conventions**: cache keys often start with `flag_` or `user_` etc—look at `helpers.get_flagname()` for example.
* **Logging**: modules often import `logging.getLogger(__name__)` and log at `.info` or `.warning`.  Logs are monitored in Railway.
* **Use of `realDictCursor`**: queries returning multiple columns usually `fetchall()` and iterate the dictionaries.

---

## 🔗 External Integrations

* **Postgres**: primary datastore; `psycopg2` driver is used.  Connection details derive from `DATABASE_URL`/`DATABASE_PUBLIC_URL`.
* **Redis / RabbitMQ**: broker for Celery tasks.  URL configured via environment variables.  `docker-compose.yml` shows how services connect.
* **Sentry**: only enabled if `SENTRY_DSN` env var is set.  Code gracefully continues if import fails.
* **Discord OAuth2**: used for user login; secrets in `DISCORD_CLIENT_SECRET`.
* **Prometheus**: optional metrics in `helpers.py` if package is installed; best‑effort.
* **Railway CLI**: available in CI for database operations; not required for daily work.

---

## 🧪 Testing Cornerstones

* Tests live under `tests/`.  Many interact with the running Flask app – `flask run` must be active.
* Database is reset between test sessions; look at `tests/conftest.py` (if present) for fixtures.
* Clean‑up after tests is critical: tests that create market offers, wars, or similar must remove them explicitly.
* Avoid using real player accounts; always use the designated tester.  If an existing test modifies global state, restore it at the end.
* Some tests depend on specific data (e.g. coalition behaviour); read the failing test names for clues.

---

## 📝 Additional Notes

* This project has extensive markdown documentation (`docs/`, multiple `.md` root files).  New features or refactors should update relevant docs.
* Performance investigations are common; refer to documents like `PERFORMANCE_OPTIMIZATIONS.md` when adding new expensive code paths.
* Historical notes in `.md` files (e.g. `PERFORMANCE_FIX_APPLIED.md`, `UI_BACKEND_INCONSISTENCIES.md`) often contain valuable context on why code is structured a certain way.

---

> **Before making any change**, run the relevant part of the app locally, exercise the code path, and if it touches the database run the corresponding tests.  Clean up any test data and double‑check performance.

Please review and let me know if any areas need clarification or if additional instructions should be included.
