# Economy and balance change log

One row per change that moves income, costs, upkeep, loot, population, influence or war range. Add the row in the same PR as the change. Fill in the outcome at 24h, 72h and 7d (Gate 8). Reverts get a row too.

| Date (UTC) | PR | Class | Change | Metric and target | Outcome | Notes |
|---|---|---|---|---|---|---|
| 2026-10-12 | #156 | D | Population 2.0 went live | Pop and income stay sane | Players reported large pop loss and "0 income" | Landed at the same moment as the distribution fix, so causes were hard to separate |
| 2026-10-12 | n/a | C | Distribution fix, same moment as Pop 2.0 | | See above | Two economy changes at once |
| 2026-10-13 | n/a | B | Income page showed zeros (display only; text ids passed to a directives batch query) | Income page matches real income | Fixed | Ticks were healthy, display bug only |
| 2026-10-20 | #212 | C | Starter population change | | Dede decided 1M starting pop is intended | Docs fixed in #214 |
| 2026-11-05 | #259 | A | Pension charged once per tick (was double-charged) | | Live | Refund for affected nations still open |
| 2026-11-05 | #267 | C | Soldier influence reduced (soldiers were about 98% of influence) | AI nations stop being top of the board | Live, announced | |
| 2026-11-05 | #271 | B | AI nations hidden from the countries list | | Live (573 to 307 listed) | Bots stay targetable |
| 2026-11-06 | #280-#283 | D | Military upkeep v2 charged from 19:00 | Upkeep derived from income | Reverted | Raids by recruit-after-tick and sell-back; players could not afford upkeep |
| 2026-11-07 | #287 | A | Revert of upkeep v2 | | Live | Dormant module kept (guard blocks deleting its test) |
