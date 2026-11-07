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

Snowball guard: income inequality (gini) may rise at most 0.03 and the income-vs-wealth log-log slope at
most 0.05. The report and `/admin/guardrails` also show the top-10% income share and the share of the
richest 10% who have been idle for over 2 days (a hibernation signal). Late-game activity is only
measured by idleness; counting what players actually do needs action logging, which does not exist yet.

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

## Money supply and faucets/sinks (economy.py)

`python -m balance.report --live ...` and `/admin/guardrails` now show:

- **Money supply:** total gold, humans vs AI, median active nation, top-10% share (from `stats`).
- **Gold created and destroyed**, last 7 days, by source, from `nation_revenue_history` (real tick data, read-only SELECT).
  Kinds: `tax` creates gold (faucet); `building_upkeep` and `pension_crisis` destroy it (sinks);
  `coalition_tax` only moves it to a coalition bank (transfer). A category the harness does not know is
  shown as `unclassified`, never dropped, and a test fails when a new ledger category has no kind.
- **Net income per hour** now subtracts loan interest due (`user_loans`, active loans). It is an upper bound
  because the tick takes at most the borrower's gold.

### What still cannot be included, and why

| Flow | Why it is missing |
|---|---|
| Loan interest in the ledger | The tick takes gold with no ledger row (`loan_interest.py`). Estimated from `user_loans` instead. Pinned by a test so a fix is noticed. |
| Market trades | Gold moves between two nations, so supply is unchanged; there is no trade ledger to attribute a per-nation net. |
| Military upkeep | Paid in resources, not gold. The gold version (v2) was reverted in #287. |
| One-off spending (buildings, units, research) | Spent at purchase time with no ledger row; not an hourly income. |
| Gifts and admin grants | Credit gold with no ledger row. |

Closing these needs a purchase and gift ledger in the game, which is a game change and out of scope here.

### N-tick conservation test

`tests/test_economy_conservation.py` runs the real hourly ticks for 24 simulated hours on real nations and checks:
every change in a nation's gold equals its ledger rows, nothing goes negative or non-finite, a repeat run in the
same period moves nothing, and the hourly result stays smooth (a jump over 25% fails). Two mutation tests prove it can
fail: an off-ledger gold leak, and a one-hour double charge (the #259 shape).

