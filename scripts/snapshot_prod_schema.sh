#!/usr/bin/env bash
# Refresh db/schema.sql (and the catalog rows in db/reference_data.sql) from
# the live production database. Read-only: pg_dump runs inside the `web`
# container because the database has no public proxy.
#
# Run after every deploy that ships a migration, then commit the result:
#   bash scripts/snapshot_prod_schema.sh && git add db/ && git commit -m "Refresh schema snapshot"
#
# Needs the Railway CLI linked to project natural-gratitude (any service).
set -euo pipefail
cd "$(dirname "$0")/.."

dump() {  # $1 = pg_dump args
  railway ssh -s web "pg_dump $1 \"\$DATABASE_URL\" 2>/dev/null | gzip | base64 -w0" 2>/dev/null \
    | tr -d '\r\n' | base64 -d | gunzip
}

tmp=$(mktemp -d)
dump "--schema-only --no-owner --no-privileges --no-comments" > "$tmp/schema.sql"
dump "--data-only --inserts --no-owner --no-privileges -t resource_dictionary -t building_dictionary -t unit_dictionary -t tech_dictionary -t gem_packages -t patreon_tiers -t cosmetics" > "$tmp/ref.sql"
dump "--data-only --inserts --no-owner -t schema_migrations" > "$tmp/sm.sql"

grep -q "CREATE TABLE public.users" "$tmp/schema.sql" || { echo "schema dump looks wrong; aborting"; exit 1; }

{
  printf -- '-- Production schema snapshot (structure only, no player data).\n'
  printf -- '-- Source: live Railway Postgres via scripts/snapshot_prod_schema.sh\n'
  printf -- '-- Taken: %s. Refresh after every migration that ships.\n' "$(date -u +%F)"
  printf -- '-- CI builds its test database from this file, so tests run against the real schema.\n\n'
  grep -vE '^\\(un)?restrict ' "$tmp/schema.sql"
} > db/schema.sql

{
  printf -- '-- Game catalog rows (resources, buildings, units, techs, store items) from production.\n'
  printf -- '-- No player data. Loaded after db/schema.sql in CI.\n\nSET session_replication_role = replica;\n'
  grep -vE '^\\(un)?restrict ' "$tmp/ref.sql"
  printf '\n-- Migrations already applied in production (so CI only runs NEW ones).\n'
  grep '^INSERT INTO public.schema_migrations' "$tmp/sm.sql"
  printf '\nSET session_replication_role = DEFAULT;\n'
} > db/reference_data.sql

rm -rf "$tmp"
echo "Updated db/schema.sql ($(grep -c '^CREATE TABLE' db/schema.sql) tables) and db/reference_data.sql"
