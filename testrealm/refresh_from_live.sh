#!/usr/bin/env bash
# Re-copy EVERY nation from the live game into the private realm (read-only on production).
# Run from the Mac, in a dir linked to the production Railway project (e.g. /Volumes/Be Careful 1/work/ano-cost).
# Nothing is written to the Mac disk: the dump streams into the vivobook RAM disk. Realm state is replaced.
set -euo pipefail
VB="${VB:-Dede@100.75.49.7}"
PYB=$(base64 <<'PY' | tr -d '\n'
import os,subprocess,sys,base64
p=subprocess.Popen(["pg_dump","--no-owner","--no-privileges","--format=custom",os.environ["DATABASE_URL"]],stdout=subprocess.PIPE)
while True:
    b=p.stdout.read(3*1024*256)
    if not b: break
    sys.stdout.write(base64.b64encode(b).decode()+"\n"); sys.stdout.flush()
sys.exit(p.wait())
PY
)
timeout 600 railway ssh --service web -- "echo $PYB | base64 -d | python3" | ssh "$VB" 'base64 -d > /dev/shm/ano_live.dump'
ssh "$VB" 'bash -s' <<'REMOTE'
set -euo pipefail
cd ~/ano-realm/ledger
docker compose -f testrealm/docker-compose.testrealm.yml -p anotest stop web worker beat
PG="docker exec -i anotest-postgres-1"
$PG psql -U ano_test -d ano_test -v ON_ERROR_STOP=1 -qc "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
$PG pg_restore -U ano_test -d ano_test --no-owner --no-privileges < /dev/shm/ano_live.dump
$PG psql -U ano_test -d ano_test -v ON_ERROR_STOP=1 -q < testrealm/scrub.sql
rm -f /dev/shm/ano_live.dump
# tester account 16 gets the shared password; every other human nation is locked until issue_login.sh is run for it
bash testrealm/set_shared_pw.sh || true
bash testrealm/lock_other_nations.sh || true
$PG psql -U ano_test -d ano_test -q < testrealm/economy_snapshot.sql
docker compose -f testrealm/docker-compose.testrealm.yml -p anotest up -d web worker beat
REMOTE
