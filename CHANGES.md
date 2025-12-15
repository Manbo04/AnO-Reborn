# Changelog for refactor/ci-and-typing

This branch contains a set of fixes, tests, and CI improvements to stabilize
the backend and make incremental progress toward full typing coverage.

Summary of major changes:
- Added many unit tests for critical flows: market, upgrades, wars, coalitions,
  and attack scripts.
- Improved compatibility for Python 3.14 AST changes with `compat.py`.
- Fixed multiple runtime bugs and test flakiness (session cookie handling,
  DB transactional fixtures, query safety).
- Upgraded `requests`/`urllib3` and added `types-requests` and `pytest-cov`.
- Added a `db-integration` CI job and updated `.github/workflows/ci.yml`.
- Added `.gitignore` cleanup and removed accidental `.coverage` commit.

Testing notes:
- Unit tests (non-DB) are in `tests/unit` and run locally by default.
- DB-backed integration tests are guarded by `RUN_DB_INTEGRATION=1` and run
  in CI against a dedicated Postgres service.

Next steps (suggested):
- Tighten mypy per package and progressively fix type issues.
- Add more integration tests for edge cases uncovered by CI.
- Run full CI and iterate on any remote failures.
