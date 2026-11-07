# Balance harness

Gate 3 of `docs/CHANGE_PIPELINE.md`. Judge a change with numbers before it ships.

```
python -m balance.report --snapshot balance/fixtures/synthetic_snapshot.json \
    --scenario "military_upkeep:0.0005" --cost 50000000
```

Scenarios (join with `+`): `flat_cost_per_hour:N`, `income_scale:F`, `military_upkeep:RATE`.
Add new ones in `balance/simulate.py`. Exit code 1 means a guardrail failed.

**MI-hour** is the gold per hour of the median active human nation. Write targets in MI-hours,
not bare gold.

**Guardrails** (thresholds in `balance/guardrails.py`, change them only in a reviewed PR):
share of active nations at net income <= 0 may rise at most 5 points; median net income may fall
at most 25%; new players may fall at most 20% and never below zero.

**Loop checks** (`balance/loops.py`): numbers for the recruit-after-tick, raid, sell-back loop and
for buy/sell round trips.

## Real data

`python -m balance.report --live --save snap.json --scenario ...` reads a **read-only**
connection from `BALANCE_DATABASE_URL`. It never uses `DATABASE_URL`. The query is a single
SELECT in a read-only session, and the saved file has no ids, names or emails.

`net_per_hour` comes from `nation_revenue_history` over 24h and covers only tax, building
upkeep, coalition tax and pension crisis. It does not include military upkeep, loans or market
trades yet. Treat results as the tax-side economy.

## Fixture

`balance/fixtures/synthetic_snapshot.json` is **synthetic** (seeded, fake). It exists so tests
run without a database. Do not read game conclusions from it. Run `--live` for real numbers.
