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

## 2. Economy code is live (Celery)

Web deploy alone does **not** update `tasks.py` in running workers. After pushing `tasks.py` / `database.py` changes:

- Railway must redeploy **celery-worker** and **beat** services, or
- Set `RAILWAY_TOKEN` in GitHub Actions so **Redeploy game stack** workflow runs on push to `master`.

Check task freshness:

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
```

## 3. Common mistakes

| Symptom | Cause |
|---------|--------|
| `/deploy-info` old SHA | GitHub deploy skipped; run `railway up` or set `RAILWAY_TOKEN` |
| `schema_compat: failed` | Boot migrations failed — read `schema_compat_errors` in `/deploy-info` |
| Login 400 | Missing CSRF — hard refresh; use Login button after reCAPTCHA |
| Resources frozen | Beat/worker not redeployed — restart beat + worker |
