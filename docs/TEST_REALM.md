# Test realm (change pipeline gate 4)

A private copy of the game with a scrubbed snapshot of real data, where a change runs for 24 to
72 hours before it reaches the live game. Ticks run, so the first-tick numbers can be compared
with the harness prediction (`balance/`).

## What exists

| Piece | File | State |
|---|---|---|
| Scrub of personal data | `testrealm/scrub.sql` | Written from a scan of `db/schema.sql`; covered by `tests/test_testrealm_scrub.py` |
| Scrub verifier | `testrealm/verify_scrub.py` | Written; not yet run against a real copy |
| Build / reset script | `testrealm/build.sh` | Written with safety rails; **not yet run** |
| Stack (Postgres, Redis, web, worker, beat) | `testrealm/docker-compose.testrealm.yml` | Written; **not yet run** |

Nothing has been provisioned, and no production data has been copied. Until the first real run,
treat the compose file and build script as untested.

## Safety rules (enforced in the scripts)

- The source is only read (`pg_dump`). Use a read-only production connection.
- The target database name must contain `test`, and must differ from the source.
- The scrub removes emails, password hashes, 2FA secrets and backup codes, verification tokens,
  recovery keys, Discord links, IP and fingerprint logs, private and free-text messages, payment
  records, and all Discord integration tables. `verify_scrub.py` then scans every text column for
  email-shaped leftovers and fails the build if any remain.
- The stack gets no credentials for Discord, email, Stripe, Patreon or Sentry, so nothing can reach
  real people.
- Nation names are public in the game and are kept. Nobody can log into a real nation unless
  `TESTREALM_SHARED_PASSWORD` is set; leave it unset if the realm is reachable from the internet.

## Where it can run (decision needed)

| Option | Cost | Notes |
|---|---|---|
| Vivobook home lab (Docker) | Free | Private by default; reachable via Tailscale. Public access needs a tunnel, which is your call. |
| Second Railway environment | Monthly cost, see `docs/RAILWAY_COST_CUT.md` | Closest to production. Do not use the default linked service: confirm `railway status` first. |

## First run (after a location is chosen)

1. Start the stack: `docker compose -f testrealm/docker-compose.testrealm.yml -p anotest up -d --build`
2. Build the database: `SOURCE_DATABASE_URL=... TEST_DATABASE_URL=postgresql://ano_test:ano_test@localhost:15432/ano_test testrealm/build.sh`
3. Check the web boot log and `http://localhost:18080/health`.
4. Sign up a new test account (or set a shared password) and click through a known page.
5. Record the result here, including anything that did not work.

## Using it in the pipeline

Class D changes deploy to the realm after Gate 3 passes. Watch the first tick, run the exploit
checklist against real-shaped data, and invite the advisory group to try to break it. Record the
outcome in the design doc before the change goes to canary on the live game.
