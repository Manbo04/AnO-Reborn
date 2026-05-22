# Progression & Smoothness Audit — 2026-05-22

Automated static audit + production HTTP smoke + test harness for account 16.
DB-backed scenarios require `DATABASE_PUBLIC_URL` (skipped in CI without Postgres).

## Executive summary

| Area | Status | Notes |
|------|--------|-------|
| Static balance | 9 findings | 0 blockers; 3 confusing retail ROI; 6 minor distribution/energy |
| Production HTTP | OK | `/country/id=16` → 200; global list routes → 302 (login) |
| Hourly tasks | Verify on prod DB | Use `scripts/progression_health_check.py` |
| Page perf | Verify on prod DB | Use `scripts/test_perf.py` (budgets in plan) |
| Test account 16 | Harness ready | `tests/test_progression_milestones.py` snapshot/restore |

---

## P0 — Blocks progression

_None confirmed in static audit._ Previously fixed: coal/oil/solar tier-1 build costs (no steel/aluminium gate on first power).

**Verify on production DB:**

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
```

If `generate_province_revenue`, `tax_income`, or `population_growth` are stale >90 minutes → resources feel frozen (P0).

---

## P1 — Misleading balance / display

| ID | Issue | Evidence |
|----|-------|----------|
| P1-1 | **Malls / banks weak gold ROI** | `progression_balance_audit.py`: malls $15,000/CG upkeep; banks $11,000/CG vs gas $1,667/CG |
| P1-2 | **Farmers markets expensive vs gas** | $80k upkeep / 16 CG vs gas $20k / 12 CG — confusing mid-game retail choice |
| P1-3 | **Dual build-cost systems** | [`province.py`](province.py) `PROVINCE_UNIT_PRICES` vs [`action_loop.py`](action_loop.py) `building_dictionary.base_cost` (steel-only quick-build) — costs can diverge |
| P1-4 | **Stale MASTER_ECONOMY_AUDIT.txt** | March snapshot shows wrong tax ($0.025), old build costs, 50k distribution caps — do not use for balance review |
| P1-5 | **Revenue display vs tasks** | Coalition tax + demographic CG in `get_revenue()` (fixed 2026-03-18); re-verify after deploy for coalition nations |

---

## P2 — Pacing / “game slows down”

| ID | Issue | Evidence |
|----|-------|----------|
| P2-1 | **Province revenue chunking** | `PROVINCE_REVENUE_CHUNK_SIZE=200` → full cycle hours = `ceil(province_count / 200)` per hour. Large empires wait 24h+ for one full pass → feels frozen |
| P2-2 | **Tax income chunking** | `TAX_INCOME_CHUNK_SIZE=250` users/hour — very large player counts may lag tax ticks |
| P2-3 | **Distribution bottleneck** | `FEATURE_RATIONS_DISTRIBUTION` on: stockpiled rations/CG useless without retail/distribution buildings |
| P2-4 | **New province demographic shock** | `pop_children = 1_000_000` on create → CG/rations demand spike until demographics rebalance |
| P2-5 | **Workforce education not enforced** | `BUILDING_EMPLOYMENT_MATRICES` education reqs marked “Future”; Chernobyl 20% floor uses total `pop_working` only |

---

## P3 — Polish

| ID | Issue |
|----|-------|
| P3-1 | `NEW_INFRA` comment typos (e.g. coal_mines “Costs $10k” vs `money: 4200`) |
| P3-2 | `bauxite_mines` strongerExplosives upgrade TODO in `tasks.py` |
| P3-3 | Global routes `/countries`, `/coalitions`, `/market` return 302 when anonymous (expected; ensure logged-in users get 200) |

---

## Early progression model (static)

From `scripts/progression_balance_audit.py`:

- Starter: **$80M gold** + 15k steel, 10k components, 10k aluminium
- Canonical early path gold total: **$37.5M** (farms → distribution → coal → mills → mines → steel → gas)
- **$42.5M** remaining for 2nd–5th provinces / military
- 1st extra province: **$8M**; 2nd: **$9.28M**
- Rough tax @ 1M pop/tick: **$500k** (before CG multiplier / coalition tax)

Early path steps still **NEED MINING** for lumber/iron/coal until extractors are built — intentional gate.

---

## Production UX smoke (2026-05-22)

| URL | HTTP |
|-----|------|
| https://affairsandorder.com/country/id=16 | 200 |
| https://affairsandorder.com/countries | 302 |
| https://affairsandorder.com/coalitions | 302 |
| https://affairsandorder.com/market | 302 |

**Friction notes (Monopoly Go checklist):**

- Anonymous users hitting Global Affairs menus get redirects — OK if login is obvious; verify logged-in test account sees 200 on all four routes.
- Hourly tick is not real-time; UI should set expectations (next revenue ~:25 UTC) to avoid “nothing changed” reports.
- After buy/sell, confirm resource panel updates without hard refresh (`invalidate_user_cache`).

---

## Tools added

| Script / test | Purpose |
|---------------|---------|
| `scripts/progression_balance_audit.py` | Static ROI, tier order, milestones (`--json`) |
| `scripts/progression_health_check.py` | `task_runs` freshness + province chunk lag |
| `scripts/test_perf.py` | Page/query timing for user 16 |
| `tests/test_progression_milestones.py` | Snapshot/restore user 16; route smoke; task delta |
| Fixed `extract_balance_report.py`, `master_economy_audit.py` | Correct `DEMO_AGING_RATES` keys |

---

## Recommended next actions (for your play session)

1. Log in as **Tester of the Game** (id 16) on production.
2. Play early path: farms → distribution → coal_burners — confirm energy unlocks processors.
3. After `:25` UTC, confirm resources/gold changed on country page.
4. Run on Railway: `python3 scripts/progression_health_check.py` and `python3 scripts/test_perf.py`.
5. For balance tuning: prioritize P1-1/P1-2 retail upkeep or bump CG output; consider raising `PROVINCE_REVENUE_CHUNK_SIZE` for top nations if P2-1 confirmed.

---

## Demographics (fixed reporting)

Per tick (now reported correctly):

- Elderly death: **0.2%**
- Working → elderly: **0.1%**
- Children → working: **2.0%**
