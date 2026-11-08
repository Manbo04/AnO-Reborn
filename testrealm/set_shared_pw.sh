set -e
cd ~/ano-realm/ledger
PW=$(cat ~/ano-realm/.realm_pw)
HASH=$(docker run --rm anotest-web:latest python -c "import bcrypt,sys;print(bcrypt.hashpw(sys.argv[1].encode(),bcrypt.gensalt()).decode())" "$PW")
echo "UPDATE users SET hash = :'h', auth_type = 'normal' WHERE auth_type <> 'bot';" | docker exec -i anotest-postgres-1 psql -U ano_test -d ano_test -v ON_ERROR_STOP=1 -v h="$HASH"
docker exec -i anotest-postgres-1 psql -U ano_test -d ano_test -tAc "select count(*), count(*) filter (where auth_type='bot') from users"
docker run --rm --network anotest_default -v $PWD:/w -w /w -e TEST_DATABASE_URL=postgresql://ano_test:ano_test@postgres:5432/ano_test -e DATABASE_URL=postgresql://ano_test:ano_test@postgres:5432/ano_test -e PG_HOST=postgres -e PG_USER=ano_test -e PG_PASSWORD=ano_test -e PG_DATABASE=ano_test anotest-web:latest python testrealm/verify_scrub.py 2>&1 | tail -4
