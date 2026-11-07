# Design doc: <short name>

- **Class:** A / B / C / D (see `docs/CHANGE_PIPELINE.md`)
- **Owner:** <who>
- **Status:** draft / in review / approved / shipped / reverted
- **Date:** <YYYY-MM-DD>

## 1. Problem (Gate 0)
- Who is affected, and how many (count from the database, not a guess):
- Evidence (ticket links, Discord links, queries):
- Success metric (one number, with today's value and the target):
- Not solving:

## 2. Facts from code (Gate 1)
Every rule quoted here links to the file and line. If a fact is not linked, it is not a fact.

| Rule | Value | Source (file:line) |
|---|---|---|
| | | |

## 3. System map
Which systems this touches and how numbers flow between them. List inputs and outputs for each.
- Income / tax:
- Upkeep / costs:
- Loot / war:
- Population / influence:
- Market / resources:
- Anything else:

If this change forces a change in another system, that change belongs in this doc.

## 4. Proposal
- What changes, in plain terms:
- Numbers, expressed in MI-hours (hours of the median active nation's net income), not bare figures:
- What the player can see (where they learn why a number moved):

## 5. Alternatives considered
1. <option> rejected because
2. <option> rejected because

## 6. Exploit review (Gate 2)
Attach the completed `EXPLOIT_CHECKLIST.md`. Summarise any loop found and the cap added.

## 7. Simulation (Gate 3)
Before / after for four archetypes. Use `python -m balance.report` on a snapshot.

| Archetype | Net income / MI-hour before | after | Time to afford X before | after | War cost per damage before | after |
|---|---|---|---|---|---|---|
| New player | | | | | | |
| Median | | | | | | |
| Whale | | | | | | |
| AI nation | | | | | | |

Guardrails (all must hold): see `balance/guardrails.py`.

## 8. Rollout and rollback (Gate 5)
- Feature flag key:
- Canary percentage and duration:
- Grace period / ramp:
- **Rollback trigger (written before shipping):** if <number> then <flip flag off / revert PR>.

## 9. Communication (Gate 7)
- Pre-announcement text and where it is posted:
- Patch note:
- Wiki pages to update:

## 10. Decision log
| Date | Who | Decision | Why |
|---|---|---|---|

## 11. Result (Gate 8)
| Check | Metric | Target | Actual | Verdict |
|---|---|---|---|---|
| 24h | | | | |
| 72h | | | | |
| 7d | | | | |
