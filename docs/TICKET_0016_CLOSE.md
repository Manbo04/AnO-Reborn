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

> Hey Dennis — sorry for the hassle. Your login username is **Primexia** (not LEVI — that's your Discord tag). I've reset your password to a temporary one and DM'd you / posted it here: **[share temp password privately]** — please log in and change it under Account.
>
> Email password reset is working again if you prefer that route (use dennis.sebalemba@gmail.com).
>
> The nation Edit/Actions tab issue is fixed on the live site — hard refresh (Cmd+Shift+R) and check Tester of the Game again; you should only see Actions when viewing someone else's nation.
>
> After you're in, generate a Backup Recovery Key from your account page so future resets are easier.

**Do not commit the temp password to git.**
