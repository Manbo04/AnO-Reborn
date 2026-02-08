# Upgrade & Runtime Notes — Dependency and Python Runtime Changes

This document explains the recent changes to runtime and dependencies, recommended actions for deployment, rollback steps, and follow-up tasks for ops/dev team.

## Summary
- We updated pinned dependencies to be compatible with modern Python runtimes (notably: Werkzeug, Jinja2, Flask, MarkupSafe, itsdangerous).
- CI now runs tests across Python 3.8, 3.10 and 3.14.
- The repository `runtime.txt` was updated to `python-3.10.19` and documentation was updated to recommend Python 3.10.x for deployments.

## Why
Older pins (e.g., `Werkzeug==0.16.0` and `Flask==1.1.2`) are incompatible with newer Python versions and caused application startup errors (TypeError during route registration) when the environment used a newer interpreter. The dependency updates restore compatibility and reduce the chance of runtime crashes on platforms that move to newer Python versions (Railway, Heroku, etc.).

## What changed (commits)
- `requirements.txt` updated (Werkzeug, Jinja2, Flask, MarkupSafe, itsdangerous)
- `runtime.txt` updated to `python-3.10.19`
- `tests/test_import_app.py` added to assert imports and DB-based test account presence (skips safely when DB not available)
- `.github/workflows/ci.yml` updated to run matrix tests on Python 3.8 / 3.10 / 3.14
- `UPGRADE_NOTES_RUNTIME.md` (this file)

## Deployment recommendation
1. Pin the Railway runtime to `python-3.10.19` in `runtime.txt`. We already updated this file.
2. Redeploy the services (web, worker, beat) so the updated `requirements.txt` is installed during the build: trigger a rebuild in Railway or push a trivial commit.
3. Verify in staging before production: 1) App starts, 2) Province page loads, 3) Buying land works for the test account.

## Rollback plan
- If the deployment fails and you must revert quickly: revert the commit that changed `requirements.txt` and `runtime.txt`, push, and trigger a rebuild.
- Note: rolling back to older packages may require pinning exact older versions and verifying they are still compatible with the chosen Python runtime.

## Follow-up tasks (optional but recommended)
- Consider shipping a `requirements-lock.txt` (pip-compile / pip-tools or poetry lock) to ensure fully reproducible builds.
- Consider a small Canary release process: deploy to a canary environment first and smoke-test critical paths (login, province page, purchase flow).
- Add a scheduled CI job that runs dependency update checks (e.g., dependabot) and posts PRs for review.

## Testing notes
- We added a smoke test `tests/test_import_app.py` that verifies `import app` succeeds and that the designated test account (user id=16) exists; the test skips safely if the DB isn't available.
- The CI matrix ensures we catch import/runtime issues across supported runtimes.

---

If you’d like, I can open a PR with these notes and link any relevant deployment tickets or add a checklist for the deployment runbook.
