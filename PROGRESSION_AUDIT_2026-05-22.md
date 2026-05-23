# Progression & Smoothness Audit — LIVE RESULTS (2026-05-22)

Executed against production Railway DB (`interchange.proxy.rlwy.net`) and `https://affairsandorder.com`.

---

## Critical: economy writes (P0) — partial recovery (2026-05-23)

**Root cause (revenue):** `generate_province_revenue()` committed `task_runs.last_run` before resource writes; education batch `integer out of range` called `conn.rollback()`, wiping uncommitted upserts; upserts omitted `updated_at`.

**Fix (branch `cursor/progression-audit-fe3b`, `tasks.py`):**
- Resource upserts **before** education; education uses **SAVEPOINT** + clamp to `MAX_INT_32`
- Upsert sets **`updated_at = now()`**
- **`last_run` only after successful commit** of province/resource work

| Signal | Last activity (2026-05-23 ~09:36 UTC) | Status |
|--------|----------------------------------------|--------|
| `user_economy.updated_at` | 2026-05-23 09:36 UTC | **OK** (after fix / manual revenue run) |
| `task_runs.generate_province_revenue` | 2026-05-23 09:36 UTC | **OK** |
| `task_runs.tax_income` | 2026-05-23 09:33 UTC | **OK** |
| `task_runs.population_growth` | 2026-05-21 07:40 UTC | **STALE** (~50h) |
| `task_runs.global_tick` | 2026-05-08 20:00 UTC | **STALE** |
| `task_runs.execute_trade_agreements` | 2026-05-08 20:00 UTC | **STALE** |
| `game_tick_logs` | 2026-05-08 20:00 UTC | **STALE** (0 ticks in last 24h) |

**Still broken:** Celery beat is not reliably firing `global_tick` (*/10), `execute_trade_agreements` (*/15), or hourly `population_growth`. Restart beat + workers on Railway; confirm schedules in `tasks.celery_beat_schedule`.

**Ops:** Merge revenue fix to `master`, deploy, then `python3 scripts/progression_health_check.py` until all rows are under 90 minutes stale.

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
```

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
```

---

## P0 — Blocks progression

| ID | Issue | Evidence |
|----|-------|----------|
| P0-1 | **Celery / hourly tasks dead** | See table above |
| P0-2 | **Tester account food deadlock** | User 16: **12.2M rations** stockpile, `food_stats = -1.0`, distribution cap **17M** vs pop **24.2M** (70% covered) — population cannot eat despite huge stockpile |
| P0-3 | **No steel production path on test nation** | User 16: **0 steel_mills**, **0 lumber_mills**, **0 distribution_centers** — cannot fix distribution/energy chain without rebuilding |

---

## P1 — Misleading balance / dual systems

| ID | Issue | Evidence |
|----|-------|----------|
| P1-1 | **Malls / banks weak gold ROI** | Static audit: malls **$15,000/CG** upkeep; gas **$1,667/CG** |
| P1-2 | **Farmers markets vs gas** | $80k/16 CG vs $20k/12 CG |
| P1-3 | **Dual build costs** | `building_dictionary.base_cost` ≈ **0.7 × gold price** in steel units (e.g. gas $7M gold → 4.9M steel quick-build) **plus** separate resource costs on province buy |
| P1-4 | **Stale MASTER_ECONOMY_AUDIT.txt** | Wrong tax, costs, distribution caps — use `variables.py` only |

---

## P2 — Pacing & gates (when tasks run again)

| ID | Issue | Evidence |
|----|-------|----------|
| P2-1 | **Distribution bottleneck** | User 16: 7.2M pop over cap; `FEATURE_RATIONS_DISTRIBUTION` on |
| P2-2 | **Chunk lag (when live)** | Top nations: 116 provinces → **~1h** full revenue cycle at 200/chunk (not the bottleneck today) |
| P2-3 | **New province demographic shock** | `pop_children = 1_000_000` on create |
| P2-4 | **Workforce education not enforced** | Employment matrices unused in task code |

---

## P3 — Polish

| ID | Issue |
|----|-------|
| P3-1 | `NEW_INFRA` comment typos |
| P3-2 | `bauxite_mines` upgrade TODO in `tasks.py` |
| P3-3 | Anonymous `/countries`, `/coalitions`, `/market` → **302** (login required) |

---

## Production HTTP (2026-05-22)

| URL | Status |
|-----|--------|
| `/country/id=16` | **200** |
| `/tutorial` | **200** |
| `/signup` | **200** (intermittent 500 observed earlier — recheck if reports continue) |
| `/countries`, `/coalitions`, `/market` | **302** logged out |

---

## User 16 snapshot (Tester of the Game)

| Metric | Value |
|--------|-------|
| Gold | $19,375,604,468 |
| Provinces | 4 |
| Population | 24,196,763 |
| Rations stockpile | 12,210,704 |
| Distribution cap | 17,000,000 (gas×2, general_stores×2, malls×2) |
| Food score | **-1.0** (shortage) |
| Key buildings | 46 farms, 6 coal_burners, 5 coal_mines, 2 malls, 2 gas, **0 distribution_centers** |

**Progression smell:** Huge rations pile but **cannot feed ~30% of pop** → growth/tax penalized; with tasks frozen, player sees no feedback loop at all.

---

## Static early-game model

- Starter **$80M** gold; canonical early path **$37.5M** gold
- No static **blockers** on tier-1 power (coal/oil/solar)
- Early path needs mining before steel/gas (intentional)

---

## Tools

| Command | Purpose |
|---------|---------|
| `python3 scripts/progression_balance_audit.py` | Static ROI / milestones |
| `python3 scripts/progression_health_check.py` | Task + economy freshness |
| `python3 scripts/run_live_progression_audit.py --http` | Full live pass |
| `python3 scripts/test_perf.py` | Query timing (user 16) |
| `pytest tests/test_progression_milestones.py` | Snapshot tests (needs DB) |

---

## Railway volume incident (ops)

- **Wrong volume `postgres-volume`:** PascalCase schema, 1 user — do **not** mount on production Postgres.
- **Correct volume `postgres-2026-05-08 20:08 UTC`:** Flask schema, 168 users — keep at `/var/lib/postgresql/data`.

See `RAILWAY_DEPLOYMENT.md` and `scripts/railway_mount_postgres_volume.sh`.

---

## Follow-up (2026-05-23) — distribution UX + retail balance

- **Country page:** `distribution_alert` banner + upkeep row (cap vs population) when stockpile cannot reach all citizens
- **Province page:** national food score drives rations check (matches tax); warns on stockpile bottleneck
- **Retail upkeep** (`NEW_INFRA`): farmers_markets $48k, banks $100k, malls $150k (was $80k / $220k / $450k)
- **Ops:** `python3 scripts/distribution_gap_report.py --user-id 16` → ~5 distribution centers needed for user 16

---

## Recommended fix order

1. **Restart Celery beat + workers** — restore `global_tick`, `execute_trade_agreements`, `population_growth`  
2. **User 16 / large nations** — build **distribution_centers** until cap ≥ population (see country alert)  
3. Monitor retail ROI feedback after upkeep reduction
