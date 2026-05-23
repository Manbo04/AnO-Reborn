# Database schema — AnO-Reborn vs Next.js volume

## Summary

**This repository (AnO-Reborn / affairsandorder.com) requires the legacy PostgreSQL schema:**

| Legacy (correct) | Next.js overhaul (wrong volume) |
|------------------|-----------------------------------|
| `users` (integer `id`) | `User` (string ids) |
| `stats`, `provinces`, `wars` | `Nation`, `Province`, … |
| `user_economy`, `resource_dictionary` | different economy model |

If migrations fail with `relation "users" does not exist`, Postgres is on the **wrong volume** — not a code bug.

---

## Do not do this

- **`python3 init_db_railway.py` on production** — drops and recreates legacy tables; **destroys** whatever is on that volume.
- **Rewrite the Python bot for Next.js** — out of scope for AnO-Reborn; the live game and this repo are Flask + legacy schema.

---

## Diagnose (30 seconds)

```bash
export DATABASE_PUBLIC_URL='postgresql://...'   # from Railway Postgres
python3 scripts/diagnose_database_schema.py
```

- **Exit 0** → correct legacy DB → continue below.
- **Exit 1** → wrong volume → fix Railway volumes before anything else.

---

## Fix wrong volume on Railway

1. **Postgres** service → **Settings** → **Volumes**.
2. Mount **exactly one** volume at `/var/lib/postgresql/data`.
3. The correct volume for Affairs & Order has tables **`users`**, **`stats`**, **`provinces`** (check via Railway **Data** / `psql` / diagnose script).
4. A volume with only **`User`**, **`Nation`** is a **different project** — detach it from this Postgres service.
5. Historical note: live player data has been on **`postgres-volume`** (~118MB+). Empty snapshots like `postgres-2026-05-08-*` must not be the only mount.
6. Redeploy **Postgres** → run diagnose again until exit 0.
7. Redeploy **web**, **celery-worker**, **beat**, **bot**.

**Postgres must run a Postgres image**, not the app Dockerfile:

- `RAILWAY_DOCKER_IMAGE=postgres:15-alpine` (or Railway managed Postgres plugin)
- Remove `RAILWAY_DOCKERFILE_PATH` from the Postgres service if set.

---

## After legacy DB is confirmed

```bash
python3 scripts/apply_discord_bot_migration.py
python3 scripts/apply_discord_guild_panels_migration.py
python3 scripts/seed_discord_guild_bindings.py \
  --guild-id 708006319658893385 \
  --admin-role-id YOUR_STAFF_ROLE_ID
```

Then in Discord: `/guild_refresh_panels`

---

## Verify game + bot use the same DB

On Railway, **web** and **bot** should both reference the **same** `DATABASE_URL` from the Postgres service.

If `https://affairsandorder.com/country/id=16` works in the browser but diagnose shows Next.js tables, web may be pointing elsewhere — check **web** → Variables → `DATABASE_URL` reference.

---

## Guild already created (708006319658893385)

Channels from setup (bind via seed script or `/guild_bind_panel`):

| Panel | Channel ID |
|-------|------------|
| readme | 1507759462147162243 |
| leaderboard | 1507759463745065000 |
| war_feed | 1507759465108078804 |
| inspector | 1507759466333077654 |
| world_status | 1507759467603820694 |
| alerts | 1507759469176684774 |

Staff channel (no panel): `#🛡️-staff-commands` → 1507759470510473407
