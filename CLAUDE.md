# AI Assistant Guidelines for AnO Project

This document defines preferences, standards, and context for all AI sessions working on this project. **Read this fully before starting any task.**

---

## 🔧 Available Tools & Access

The AI has access to:
- **GitHub MCP** - Repository management, PRs, issues, branches
- **Railway** - Production database via `DATABASE_PUBLIC_URL`
- **ano-game MCP** - Direct game database queries (nations, resources, wars, etc.)
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

### On Testing
1. **Use the designated test account for ALL testing**: `Tester of the Game` (user ID: 16)
2. **Never test on real player accounts** - always query/modify the test account
3. **The test account has 2 provinces** for multi-province scenario testing
4. **Reset test account state after major tests** if needed
5. **LEAVE NO TRACE** - All test data MUST be cleaned up after testing:
   - Delete any test market offers created
   - Reverse any resource changes made
   - Remove any test wars/declarations
   - Undo coalition changes
   - Restore original values for any modified fields
   - **Record original state BEFORE testing, restore it AFTER**

### On Communication
1. **Don't ask permission repeatedly.** If a task is given, complete it.
2. **Don't list what you're "about to do"** - just do it.
3. **Be concise.** Skip unnecessary preamble.
4. **Show results, not intentions.**

---

## 📋 Project Context

### Tech Stack
- **Backend**: Flask (Python 3.10)
- **Database**: PostgreSQL on Railway
- **Task Queue**: Celery with Redis
- **Deployment**: Railway (auto-deploys on push to master)
- **Error Tracking**: Sentry

### Key Files
- `app.py` - Main Flask app, template filters, routes registration
- `province.py` - Province management (common source of issues)
- `tasks.py` - Celery background tasks (revenue generation, etc.)
- `database.py` - DB connection, caching utilities
- `variables.py` - Game constants, infrastructure definitions
- `helpers.py` - Shared utilities, decorators

### Common Issue Patterns
- **500 errors**: Usually Jinja2 template syntax or None values in templates
- **Missing data**: Check LEFT JOINs, some users have incomplete data
- **Performance**: Watch for N+1 queries, use the optimized patterns in database.py

---

## 🔄 Session Handoff Protocol

At the end of each session or major task, document:

### What Was Done
- List specific files changed and why
- Commits made with their hashes

### What To Watch
- Any areas that might need follow-up
- Related code that wasn't fully tested
- Edge cases that weren't covered

### Next Steps
- Pending improvements identified during the work
- Technical debt noted
- User-reported issues not yet addressed

---

## 📝 Current Session Log

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

## 🛠️ Development Commands

```bash
# Run locally
export DATABASE_PUBLIC_URL='postgresql://...'
./venv310/bin/python -m flask run

# Run tests
./venv310/bin/python -m pytest tests/

# Check template syntax
./venv310/bin/python -c 'from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader("templates")); env.get_template("province.html")'

# Query production database
./venv310/bin/python -c 'from database import get_db_connection; ...'

# Deploy
git push origin master  # Railway auto-deploys
```

---

## 🚫 Anti-Patterns to Avoid

1. **Don't create summary markdown files** after each task unless explicitly requested
2. **Don't ask "would you like me to..."** - just do it
3. **Don't provide code blocks** for the user to copy - use the edit tools
4. **Don't suggest manual steps** when automation is possible
5. **Don't leave TODOs in code** without addressing them

---

## ✅ Quality Checklist (Before Marking Complete)

- [ ] Code runs without errors
- [ ] Tested with real data from production database
- [ ] No regressions in related functionality
- [ ] Follows existing code patterns
- [ ] Committed and pushed (if deployment needed)
- [ ] Session log updated in this file
# Trigger deploy Tue Feb  3 20:59:35 CST 2026
