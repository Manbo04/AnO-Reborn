#!/usr/bin/env bash
# Realm only. Usage: testrealm/issue_login.sh "<nation username>"   -> sets a fresh random password for that ONE nation and prints it.
# Run on the vivobook. Every other nation keeps an unusable password until you issue one.
set -euo pipefail
U="${1:?nation username}"
PW=$(python3 -c 'import secrets;print(secrets.token_urlsafe(9))')
HASH=$(docker run --rm anotest-web:latest python -c "import bcrypt,sys;print(bcrypt.hashpw(sys.argv[1].encode(),bcrypt.gensalt()).decode())" "$PW")
N=$(echo "UPDATE users SET hash = :'h', auth_type='normal' WHERE username = :'u' AND auth_type <> 'bot' RETURNING id;" | docker exec -i anotest-postgres-1 psql -U ano_test -d ano_test -Atq -v h="$HASH" -v u="$U")
[ -n "$N" ] || { echo "no such human nation: $U" >&2; exit 1; }
echo "nation id $N  password: $PW"
