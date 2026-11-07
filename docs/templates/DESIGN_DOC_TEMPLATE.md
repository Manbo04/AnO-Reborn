# Design doc: <short name>

- **Class:** A / B / C / D (see `docs/CHANGE_PIPELINE.md`)
- **Owner:** <who>
- **Status:** draft / in review / approved / shipped / reverted
- **Date:** <YYYY-MM-DD>

## 0. Core pillars (required)
Name the game pillars this change serves (for example: meaningful choices, small players can still win, wars have consequences, the economy rewards activity). State which pillar it strengthens and which it could weaken. A change that serves no pillar is not ready.

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

## 4b. Progression curve, snowball and staleness
- **Curve shape:** new players should progress fast (cheap early provinces, land, cities, buildings) and growth should taper as a nation gets large. Describe the curve this change gives and attach the harness curve numbers (income inequality, income-vs-wealth slope).
- **Snowball check:** can the leader convert a lead into a bigger lead with no limit (loot, compounding income, cheaper everything)? What slows them?
- **Staleness check:** a good curve alone does not stop a game going stale. What does a late-game nation do besides grow? Name the second game for late players (conflict, diplomacy, projects, trade, rivalry) this change feeds or ignores.
- **Hibernation check:** does the change make late players wait between upgrades with nothing to do? Attach the share of top-decile nations idle for more than 2 days.
- **Mechanics checks:** probability and RNG used (what variance, can it be farmed), player psychology (what will players feel and do), and who the audience is (daily-check players, not constant players).

## 4c. Late-game substance, skill and dead time
Progression attracts players; substance keeps them once growth slows.
- **Late-game substance check:** what does a top-decile player do with their time after growth slows? "Grow more" is not an answer; a doc that says only that is rejected. Name the activity (war, diplomacy, coalition projects, trade, rivalry).
- **Skill-improvement check:** does this give players something to get better at, not just wait for or spend on? Say what skill and how a better player shows it.
- **Dead-time audit:** list every timer and cooldown this adds (build, research, training, cooldown) and what the player can do while it runs. Any added waiting with nothing else to do must be removed, shortened, or paired with other activity.

| Timer / cooldown | Length | What the player can do meanwhile |
|---|---|---|
| | | |

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
