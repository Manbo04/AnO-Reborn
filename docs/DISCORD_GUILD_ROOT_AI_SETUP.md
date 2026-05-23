# Discord Guild Panels — Root AI Setup Playbook

This guide is for a **root AI agent** (or server owner) configuring an **Affairs & Order** Discord server with Locutus-style **channel panels** and **staff-only admin commands**.

The bot lives in `discord_bot/` and reads live data from the same PostgreSQL database as the game.

---

## Goals

1. Create a themed channel category (like a “war room” / “global affairs” wing).
2. Bind **auto-updating embed panels** in each channel.
3. Ensure **`/admin_*` and `/guild_*` commands are unusable by regular players**.
4. Keep player commands (`/register`, `/me`, `/nation`, `/wars`, `/resources`) available to everyone.

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Bot invited | OAuth scope `bot` + `applications.commands` |
| Bot permissions | Manage Messages, Pin Messages, Send Messages, Embed Links, Use Slash Commands |
| Railway / hosting | `bot` service: `DATABASE_URL`, `DISCORD_BOT_TOKEN`, optional `REDIS_URL` |
| Migrations | `0022_discord_bot.sql` + `0023_discord_guild_panels.sql` (or boot `ensure_schema_compat`) |
| Staff Discord role | e.g. `@Council` or `@Staff` — not given to regular players |

Optional env on bot service:

```bash
DISCORD_ADMIN_ROLE_IDS=123456789012345678,987654321098765432
```

---

## Phase 1 — Discord server layout (human or AI with Manage Channels)

Create a category: **`Affairs & Order`**.

Create text channels (names are suggestions; emojis match AnO theme):

| Channel | Panel key | Who can view |
|---------|-----------|--------------|
| `#📜-bot-guide` | `readme` | Everyone |
| `#🏆-influence-board` | `leaderboard` | Everyone |
| `#⚔️-war-feed` | `war_feed` | Everyone |
| `#🔬-nation-inspector` | `inspector` | Everyone |
| `#🌍-global-affairs` | `world_status` | Everyone |
| `#📢-realm-alerts` | `alerts` | Everyone |
| `#🛡️-staff-commands` | _(none — staff reference only)_ | **Staff role only** |

### Lock down staff channel

1. Open `#🛡️-staff-commands` → **Edit Channel** → **Permissions**.
2. `@everyone` → deny **View Channel**.
3. Your staff role → allow **View Channel**, **Send Messages**.
4. Post a pinned note: “Staff slash commands work in any channel, but only for users with Administrator or the configured staff role.”

---

## Phase 2 — Database

On Railway (or locally with `DATABASE_PUBLIC_URL`):

```bash
python3 scripts/apply_discord_bot_migration.py
python3 scripts/apply_discord_guild_panels_migration.py
```

Or rely on web/bot boot calling `ensure_schema_compat()` (adds columns idempotently).

---

## Phase 3 — Deploy bot code

Ensure `bot` service uses:

- **Dockerfile**: `Dockerfile.discord-bot`
- **Start**: `python scripts/run_discord_bot_if_leader.py`
- **Env**: `DISCORD_BOT_TOKEN`, `DATABASE_URL` (reference Postgres)

After deploy, logs must show:

```text
Synced N global slash command(s)
data mode=database
```

`N` should be **12+** (player commands + `guild_*` + `admin_*` groups).

---

## Phase 4 — Bind panels (staff runs in Discord)

A user with **Administrator** (or configured staff role) runs these **in each channel**:

```
/guild_bind_panel panel:readme          → in #📜-bot-guide
/guild_bind_panel panel:leaderboard    → in #🏆-influence-board
/guild_bind_panel panel:war_feed       → in #⚔️-war-feed
/guild_bind_panel panel:inspector      → in #🔬-nation-inspector
/guild_bind_panel panel:world_status   → in #🌍-global-affairs
/guild_bind_panel panel:alerts         → in #📢-realm-alerts
```

Each command:

1. Stores the channel id in `discord_guild_settings`.
2. Posts (or updates) a pinned embed.
3. Saves message id in `discord_panel_messages`.

Then run once:

```
/guild_refresh_panels
```

Verify `/guild_panel_status` lists all six bindings.

---

## Phase 5 — Configure staff role (recommended)

```
/guild_set_admin_role role:@YourStaffRole
```

This writes `discord_role_aliases` (`alias = admin`). Users with that role **or** Discord Administrator **or** `Manage Guild` may run:

- `/guild_*` — panel configuration
- `/admin_*` — broadcasts, nation intel, whois

**Regular players** attempting these commands receive:

> This command is restricted to server administrators and configured staff roles.

Discord also hides commands marked `default_permissions=Administrator` from users without admin — defense in depth.

---

## Phase 6 — Admin command reference (staff only)

| Command | Purpose |
|---------|---------|
| `/admin_broadcast message:...` | Post to alerts channel + refresh alerts panel |
| `/admin_nation identifier:...` | Full nation embed (any id/name) |
| `/admin_whois member:@User` | Nation linked to Discord user |
| `/admin_refresh_all_panels` | Refresh panels in all configured guilds |
| `/guild_refresh_panels` | Refresh this server only |
| `/guild_panel_status` | Show bindings |
| `/guild_setup_guide` | Reprint channel blueprint |

Player commands remain **unaffected**.

---

## Phase 7 — Automation

- Panels auto-refresh every **15 minutes** while the bot is online (`panel_refresh_loop` in `discord_bot/main.py`).
- Change interval: `panels_refresh_minutes` column on `discord_guild_settings` (future UI; default 15).

---

## Phase 8 — Verification checklist

- [ ] Non-admin account: `/me` works; `/admin_broadcast` **fails** or hidden.
- [ ] Admin account: `/guild_panel_status` shows six channels.
- [ ] Leaderboard panel shows top gold nations with links to country pages.
- [ ] War feed updates when wars are active in DB.
- [ ] Inspector shows nation/province/war counts and last revenue tick.
- [ ] Readme panel documents `/register` flow.
- [ ] `#🛡️-staff-commands` invisible to `@everyone`.

---

## Coalition servers (optional)

Table `discord_guild_settings.coalition_id` can link a guild to an in-game coalition (`colNames.id`) for future alerts (bank/war channels: `bank_alert_channel_id`, `war_alert_channel_id`). Phase 2 alerts are not yet wired to live events — panels poll the database.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Slash commands missing | Re-invite bot with `applications.commands`; wait up to 1h for global sync |
| Panels empty / errors | Check bot logs; confirm `DATABASE_URL` on bot service |
| Admin commands visible to everyone | Discord caches permissions — kick/re-invite bot or use role override |
| Pin failed | Bot needs **Manage Messages** + **Pin Messages** in channel |
| Migration missing columns | Run `0023` or restart bot after `ensure_schema_compat` update |

---

## File map (for maintainers)

| Path | Role |
|------|------|
| `discord_bot/panels/builders.py` | AnO-themed embeds |
| `discord_bot/panels/data.py` | SQL snapshots for panels |
| `discord_bot/panel_service.py` | Post/edit/pin messages |
| `discord_bot/guild_store.py` | Guild config persistence |
| `discord_bot/permissions.py` | Admin checks |
| `discord_bot/commands/guild_setup.py` | `/guild_*` |
| `discord_bot/commands/admin_cmds.py` | `/admin_*` |
| `migrations/0023_discord_guild_panels.sql` | Schema |

---

## Root AI one-shot script (outline)

An autonomous agent with Discord + Railway access should:

1. Confirm bot deployed from `master` with `Dockerfile.discord-bot`.
2. Apply migrations if `discord_panel_messages` missing.
3. Create category + seven channels (table above).
4. Set `#🛡️-staff-commands` permissions (deny @everyone view).
5. Execute six `/guild_bind_panel` bindings via staff test account (or instruct owner).
6. Run `/guild_set_admin_role` and `/guild_refresh_panels`.
7. Post verification screenshot checklist to staff channel.

Done.
