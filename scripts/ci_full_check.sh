#!/usr/bin/env bash
# The "prod-shaped" CI gate. Runs against a disposable Postgres:
#   1. build the DB from the production schema snapshot (db/)
#   2. apply any NEW migrations -- must succeed (strict)
#   3. every SQL query in the app must match the resulting schema
#   4. the WHOLE test suite must pass (except tests/known_failures.txt)
# Run locally with DATABASE_URL pointing at a throwaway database.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"

echo "::group::Load production schema snapshot"
"$PY" scripts/load_schema_snapshot.py
echo "::endgroup::"

echo "::group::Migration names"
"$PY" scripts/apply_all_pending_migrations.py --check-names
echo "::endgroup::"

echo "::group::Apply new migrations (strict)"
"$PY" scripts/apply_all_pending_migrations.py --strict
echo "::endgroup::"

echo "::group::SQL vs production schema"
"$PY" scripts/check_sql_against_schema.py
echo "::endgroup::"

echo "::group::Full test suite"
"$PY" -m pytest tests -p no:cacheprovider --timeout=120 -rfE
echo "::endgroup::"
