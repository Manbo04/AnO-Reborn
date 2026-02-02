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
