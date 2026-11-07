# Test realm (change pipeline gate 4)

A private copy of the game with a scrubbed snapshot of real data, where a change runs for 24 to
72 hours before it reaches the live game. Ticks run, so the first-tick numbers can be compared
with the harness prediction (`balance/`).

## What exists

| Piece | File | State |
|---|---|---|
| Scrub of personal data | `testrealm/scrub.sql` | Run on a real production copy 2026-11-07; covered by `tests/test_testrealm_scrub.py` |
| Scrub verifier | `testrealm/verify_scrub.py` | Passed on the real copy (365 text columns, no emails, tokens or 2FA left) |
| Build / reset script | `testrealm/build.sh` | Steps run by hand on the first build (see below); the script itself is untested end to end |
| Stack (Postgres, Redis, web, worker, beat) | `testrealm/docker-compose.testrealm.yml` | Running on the vivobook, boots clean, `/health` 200 |
| Staging helper | `testrealm/stage_war.py` | Declares a war, checks the sell block, ends the war, checks selling again |

## Where it runs (decided 2026-11-07)

On the vivobook home lab with Docker. Free, private, bound to `127.0.0.1:18080` on the vivobook, so it
is not reachable from the internet. Reach it with an ssh tunnel (`ssh -L 18080:127.0.0.1:18080 <vivobook>`)
or from the vivobook desktop. Opening it to players needs a tunnel and a decision from Dede, and the
shared tester password must then be replaced.

A second Railway environment stays the alternative if the realm ever needs a public address
(cost: see `docs/RAILWAY_COST_CUT.md`).

## First run, 2026-11-07 (what happened)

1. Started Postgres and Redis from the compose file.
2. Copied production straight into the realm database with `pg_dump` run inside a production container,
   streamed over ssh into the vivobook's RAM disk (33 MB, never on a disk). Restored it, ran `scrub.sql`,
   deleted the dump, ran `verify_scrub.py`: passed.
3. Built and started web, worker and beat. Clean boot logs, `/health` 200.
4. Fixes needed: the login captcha rejected every login (set `SKIP_RECAPTCHA`, honoured only outside
   PROD), and accounts with a non-password `auth_type` could not use the shared password (the build script
   now sets `auth_type = 'normal'` when it sets the shared password).
5. Staged check: logged in as the test account, declared war on an AI nation, confirmed a negative-quantity
   sell is blocked at war and allowed after the war ends. Passed.

## Rebuild or reset

Repeat step 2 (restore, scrub, verify, set the shared password) and restart the stack. Keep the shared
password in a file on the vivobook only, never in the repo. The realm database holds a scrubbed copy of
real nations (names, stats, wars), so treat it as private.

## Staging a state (war, second player)

`python3 testrealm/stage_war.py` (see its header for the environment it expects) logs in as the test
account, picks an AI nation in war range with no truce, and runs the war-sell check both ways. Use the same
pattern for any feature that needs a second player: stage the state, run the checks, end the state.

## Using it in the pipeline

Class D changes deploy to the realm after Gate 3 passes. Watch the first tick, run the exploit
checklist against real-shaped data, and invite the advisory group to try to break it. Record the
outcome in the design doc before the change goes to canary on the live game.
