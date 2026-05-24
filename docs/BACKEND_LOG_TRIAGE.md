# Backend log triage (auto-generated)

- Files: README.md
- Lines scanned: 15

## Bucket counts

| Bucket | Hits |
|--------|------|
| HTTP_500 | 0 |
| LOGIN | 0 |
| SCHEMA | 0 |
| DB_POOL | 0 |
| CELERY_BEAT | 0 |
| CELERY_TASK | 0 |
| ECONOMY | 0 |
| MARKET_COALITION | 0 |
| CSRF | 0 |

## Top signatures (normalized)


## Suggested priority

1. **LOGIN** / **HTTP_500** on `POST /login` — policies row ensure, CSRF token on form
2. **SCHEMA** — run `apply_all_pending_migrations.py`, verify `/deploy-info`
3. **CELERY_BEAT** / **ECONOMY** — beat leader lock, `progression_health_check.py`
4. **DB_POOL** — pool size vs replica count
