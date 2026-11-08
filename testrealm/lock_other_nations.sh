set -e
cd ~/ano-realm/ledger
H=$(docker run --rm anotest-web:latest python -c "import bcrypt,secrets;print(bcrypt.hashpw(secrets.token_hex(24).encode(),bcrypt.gensalt()).decode())")
echo "UPDATE users SET hash = :'h' WHERE auth_type <> 'bot' AND id <> 16;" | docker exec -i anotest-postgres-1 psql -U ano_test -d ano_test -q -v h="$H"
docker exec -i anotest-postgres-1 psql -U ano_test -d ano_test -Atc "DELETE FROM ledger_snapshots WHERE ts=(SELECT min(ts) FROM ledger_snapshots) AND (SELECT count(*) FROM ledger_snapshots)>1"
