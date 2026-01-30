Title: Canonicalize Economy.get_particular_resources

Summary:
- Consolidated `get_particular_resources` to a single robust implementation in `attack_scripts/Nations.py`.
- Added an import-time rebind and a cross-module patch to update any existing `Economy` class objects in `sys.modules`.
- Added a minimal, documented test-time guard in `tests/test_economy_resources.py` (temporary safety net).

Validation:
- Full test suite passed locally on 29 Jan 2026.
- Commit: 95d28faa (see repo history)

Follow-ups:
- Remove the test-time guard after a couple of consecutive green CI runs.
- Optionally add a lightweight import-time self-check to detect regressions.

Notes:
This file is intentionally small and only serves to provide context in the PR for reviewers and linkage to the commit(s) already present on `master`.
