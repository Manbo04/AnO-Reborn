# Progression & Smoothness Audit — LIVE RESULTS (2026-05-22)

Executed against production Railway DB (`interchange.proxy.rlwy.net`) and `https://affairsandorder.com`.

---

## Critical: economy writes frozen (P0)

**Resource rows have not been updated since 2026-05-08 ~20:00 UTC** (`user_economy.updated_at` max).

| Signal | Last activity | Status |
|--------|---------------|--------|
| `user_economy.updated_at` | 2026-05-08 20:00 UTC | **STALE — no resource commits** |
| `game_tick_logs` | 2026-05-08 20:00 UTC | **STALE** |
| `task_runs.global_tick` | 2026-05-08 20:00 UTC | **STALE** |
| `task_runs.execute_trade_agreements` | 2026-05-08 20:00 UTC | **STALE** |
| `task_runs.population_growth` | 2026-05-21 07:35 UTC | Stale ~48h |
| `task_runs.tax_income` / `generate_province_revenue` | May update when manually triggered | **`task_runs` can advance without `user_economy` changing** |

**Player impact:** Stockpiles and gold do not move from hourly play. Manual/admin task triggers may bump `task_runs` timestamps without applying deltas — investigate task completion vs commit path.

**Ops action:** Restart Celery beat + workers; run one revenue cycle; confirm `user_economy.updated_at` moves within 75 minutes.

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

## Recommended fix order

1. **Restart economy workers** (P0-1) — verify `task_runs` within 1 hour  
2. **User 16 playtest** after tick restore — buy **distribution_centers** or more retail to cover 24M pop  
3. Balance pass on retail ROI (P1-1, P1-2) once economy moves again  
4. UI: show distribution cap vs population when `food_stats < 0`
