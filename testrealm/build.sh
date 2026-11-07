#!/usr/bin/env bash
# Build or reset the test realm database from a read-only copy of production, then scrub it.
#
#   SOURCE_DATABASE_URL=...  read-only connection to production (never written to)
#   TEST_DATABASE_URL=...    the test copy; its database name must contain "test"
#   TESTREALM_SHARED_PASSWORD=...  optional; lets testers log into any scrubbed nation
#
# Safety rails: refuses if the two URLs are equal or the target name lacks "test"; the source is
# only ever read by pg_dump; the scrub runs only on the target; the result is verified.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${SOURCE_DATABASE_URL:?set SOURCE_DATABASE_URL (read-only production)}"
: "${TEST_DATABASE_URL:?set TEST_DATABASE_URL (the test copy)}"

if [ "$SOURCE_DATABASE_URL" = "$TEST_DATABASE_URL" ]; then
  echo "Refusing: source and target are the same database." >&2; exit 2
fi
TARGET_URL="${TEST_DATABASE_URL%%\?*}"; TARGET_NAME="${TARGET_URL##*/}"
case "$TARGET_NAME" in
  *test*) ;;
  *) echo "Refusing: target database name '$TARGET_NAME' must contain 'test'." >&2; exit 2 ;;
esac

DUMP="$(mktemp -t ano_realm_XXXXXX).dump"
trap 'rm -f "$DUMP"' EXIT

echo "1/5 dumping production (read-only)"
pg_dump --no-owner --no-privileges --format=custom --file="$DUMP" "$SOURCE_DATABASE_URL"

echo "2/5 resetting test database schema"
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "3/5 restoring into the test database"
pg_restore --no-owner --no-privileges --dbname="$TEST_DATABASE_URL" "$DUMP"

echo "4/5 scrubbing personal data"
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f testrealm/scrub.sql
if [ -n "${TESTREALM_SHARED_PASSWORD:-}" ]; then
  HASH="$(python3 -c 'import bcrypt,sys;print(bcrypt.hashpw(sys.argv[1].encode(),bcrypt.gensalt()).decode())' "$TESTREALM_SHARED_PASSWORD")"
  psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -v h="$HASH" -c "UPDATE users SET hash = :'h', auth_type = 'normal' WHERE auth_type <> 'bot'"
  echo "   shared tester password set"
fi

echo "5/5 verifying the scrub"
python3 testrealm/verify_scrub.py
echo "Test realm database ready."
