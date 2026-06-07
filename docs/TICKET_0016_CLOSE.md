# Ticket #0016 — Resolution notes (Dennis Sebalemba / Primexia)

## Root cause

Dennis was logging in with username **LEVI** (Discord tag). His in-game nation/username is **Primexia** (user id 547, email dennis.sebalemba@gmail.com).

A PostgreSQL collation issue also prevented `username = %s` equality matches for some accounts; login now uses `trim(username)=trim(%s)`.

## Actions taken

1. Restored web service (was 502 / failed deploy).
2. Set `RESEND_API_KEY` and `BASE_URL` on Railway web — email password reset re-enabled.
3. Reset Primexia password (admin); Dennis should change it after login.
4. Deployed login fixes: `COALESCE(auth_type,'normal')`, `trim(username)` matching.
5. Nation tab gating verified on production (foreign nations show Actions only).
6. Removed dead `edithide` JS helpers; fixed `send_password_reset_email` URL path.
7. Redeployed web, celery-worker, beat, and bot.

## Suggested Discord reply

> Hey Dennis — sorry for the hassle. Your login username is **Primexia** (not LEVI — that's your Discord tag).
>
> Email password reset is working again at https://affairsandorder.com/forgot_password — use **dennis.sebalemba@gmail.com**.
>
> Backup recovery keys were never auto-issued to older accounts, so you wouldn't have received one in email. That wasn't your fault. After you log in, open **Account** and generate a Backup Recovery Key so you have one saved for next time.
>
> The nation Edit/Actions tab issue is fixed on the live site — hard refresh (Cmd+Shift+R) and check Tester of the Game again; you should only see Actions when viewing someone else's nation.

## Recovery key fixes deployed

- `recovery_key` column added via schema compat + migration `0034_add_users_recovery_key.sql`
- Forgot-password page: email primary; recovery key collapsed under "Have a saved recovery key?"
- Recovery reset uses `trim(username)` and clearer errors when no key exists
- New signups receive a one-time recovery key on `/save_recovery_key`
- Account page shows a banner when no recovery key is on file
- Support script: `python3 scripts/admin_password_reset_link.py --username Primexia`

**Do not commit the temp password to git.**
