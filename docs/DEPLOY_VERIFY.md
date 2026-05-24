# Verify fixes reached players

## 1. Web code is live

```bash
curl -sS https://affairsandorder.com/deploy-info | python3 -m json.tool
```

Expect:

- `git_commit` matches latest `master` on GitHub
- `schema_compat`: `ok` (not `failed`)
- `start_command`: `start_production.sh`
- No `schema_compat_errors` array
- `economy_tasks.generate_province_revenue.stale`: `false` (or `age_seconds` under 7200)

## 2. Economy code is live (Celery)

Web deploy alone does **not** update `tasks.py` in running workers. After pushing `tasks.py` / `database.py` changes:

- Railway must redeploy **celery-worker** and **beat** services, or
- Set `RAILWAY_TOKEN` in GitHub Actions so **Redeploy game stack** workflow runs on push to `master`.

Check task freshness:

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
```

## 3. Static UI reached players

After CSS/template changes, confirm cache-bust and deploy commit in HTML:

```bash
curl -sS https://affairsandorder.com/ | grep -E 'deploy-commit|style.css\?v='
```

Expect `style.css?v=` to match the short git SHA from `/deploy-info` (not a hand-edited `v=23`).

CSS should **not** return `immutable` in Cache-Control (that trapped players on month-old styles).

## 4. Common mistakes

| Symptom | Cause |
|---------|--------|
| `/deploy-info` old SHA | GitHub deploy skipped; **set `RAILWAY_TOKEN` in GitHub secrets** or run `railway up` |
| Redeploy workflow green but no deploy | `RAILWAY_TOKEN` empty — workflow exits 0 with warning only |
| UI fix on GitHub but players see old layout | Service worker or `immutable` CSS cache — fixed in fa693a04+; needs deploy |
| `schema_compat: failed` | Boot migrations failed — read `schema_compat_errors` in `/deploy-info` |
| Login 400 | Missing CSRF — hard refresh; use Login button after reCAPTCHA |
| Resources frozen | Beat/worker not redeployed — restart beat + worker |
