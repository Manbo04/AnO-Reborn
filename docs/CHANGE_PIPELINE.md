# A&O Change Pipeline

Modelled on how studios run live games: stage-gates, design docs with a decision log, a public test realm, staged rollout with a kill switch, telemetry-led balance, and post-mortems. Sources of the practices are named in each gate.

## 0. What the players told us (evidence, not opinion)

JoshMD, Discord, 2026-10-03 to 2026-11-07. He warned about problems before they shipped.

| Date | What he said | What happened later | Gate that would have caught it |
|---|---|---|---|
| 10-12 | Standing military gives score and full refund, so sell, hit smaller, rebuy at no cost | Same sell-back loop reappeared 11-06 with upkeep | G2 exploit review |
| 10-05 | Drones/missiles/nukes use no supply and cost no morale, so they can be spammed | Iron dome / nuke cap work 10-24, still unfinished | G2, G5 |
| 10-24 | Surrender, ally-join timing, MDP unlimited range | Open design debts | G1 design doc, G4 playtest |
| 11-06 | Recruit one of each unit after the tick, raid, sell back: "free war wins" | Upkeep v2 reverted in #287 | G2, G3 simulation |
| 11-06 | "Influence isn't war range, it's pop" | Dev statement was wrong | G1 fact-check against code |
| 11-06 | Higher purchase cost changes nothing; "what are we even trying to solve" | No problem statement existed | G0 |
| 11-06 | Fixing military cost forces income, building and land costs up: economy needs a system rework | Piecemeal edits | G1 system map |
| 11-07 | Every balance update made things worse and got reverted or re-changed | #212 pop, Pop 2.0 income display, upkeep v2 | whole pipeline |
| 11-07 | Beta label is misleading | Dede decided: whole game is the beta | G7 communication, release channel naming |
| 10-05 | Unrest grows and falls with no visible reason | UI gap | G1 "player can see why" rule |

Common root causes: no stated problem, unchecked facts, no exploit review, no simulation, no staged rollout, no rollback trigger, and no explanation to players.

## 1. Principles (the rules the gates enforce)

1. **Problem before solution.** Every change cites evidence (data, tickets, vote) and a measurable target.
2. **Facts from code, not memory.** Any number or rule quoted in a design is linked to the file and line.
3. **Every change is an experiment.** It has a hypothesis, a metric, a threshold, and a rollback.
4. **Systems, not patches.** Changes are placed on a system map first (economy, military, war, population). If a change forces a second change elsewhere, both go in one design.
5. **Players are testers, not victims.** Large changes get visibility before they go live, and a path for feedback.
6. **Reversible by default.** Anything that touches the economy ships behind a flag or with a prepared revert.
7. **Say what you did.** Every shipped change gets a plain-language note with the reason.

## 2. Change classes (decides how many gates apply)

| Class | Examples | Gates |
|---|---|---|
| **A: Hotfix** | Crash, display bug, exploit actively draining economy | G5, G6, G8 (retro within 48h) |
| **B: Fix / QoL** | UI clarity, tooltip, small bug, non-economic | G0 (one line), G4-lite, G5, G6, G7 |
| **C: Tuning** | Cost, rate, cap inside an existing signed pillar | G0 to G8, simulation required, fast-track design (one page) |
| **D: System** | New mechanic, upkeep, war rules, population, economy rework | All gates, full design doc, soak time, playtest, staged rollout |

Rule: if unsure, round up one class. Anything that changes income, upkeep, loot, or war range is at least class C.

## 3. The gates

### G0: Intake and problem statement (Product discovery)
Studio practice: problem framing / opportunity assessment before concept.
- One-page *Problem Statement*: who is affected, evidence (tickets, Discord links, DB counts), what success looks like as a number, what we are not solving.
- Sources, ranked: telemetry anomalies, exploit reports, Friday vote results, support tickets, Dede's priorities.
- Output: a backlog item with ID, class (A to D), owner, and the metric it will be judged on.
- **Fail:** can't state the metric = not ready.

### G1: Design doc and system map (Pre-production, GDD, RFC)
Studio practice: game design document, design pillars, RFC with a decision log (as in Paradox dev diaries, Riot design posts).
- **System map:** which pillars and tables the change touches and which formulas it feeds into (income, tax, upkeep, loot, influence, war range, morale, supply). Draw inputs and outputs.
- **Fact table:** each quoted rule with code reference. Example: war range uses population, not influence.
- **Anchor all numbers to the MI-hour** (hours of median active nation's net income), per the balance spec. No bare numbers.
- **Alternatives considered** (at least two) and why rejected.
- **Player-legibility rule:** the player can see why a number changed (the unrest lesson).
- **Decision log:** who decided, when, what changed since.
- **Fail:** any claim without a code reference, or any second-order effect left as "we'll see".

### G2: Exploit and abuse review (Red team, design review)
Studio practice: adversarial design review; economy teams in MMOs run "dupe and arbitrage" reviews before launch.
Mandatory checklist, results written into the doc:
- Timing: act just after or before the tick, mid-war, mid-truce.
- Sell-back and refund loops (buy, use, sell). Must be net-negative or capped.
- Alts and self-targeting; allies funnelling resources; coalition snowballing.
- Loot snowball: does one win compound into permanent first place?
- Zero, negative, and huge inputs; double-submit; race conditions.
- Cheapest unit/building that satisfies a requirement (the "one of each unit" case).
- AI nations and hidden nations: do they hit the same rule?
- Dormant, new, and whale accounts at the same time.
- **Fail:** any positive-expected-value loop with no cap. Back to G1.

### G3: Simulation and balance gate (Telemetry-driven balance)
Studio practice: Riot and Blizzard review win-rate and pick-rate bands and run internal sims before touching live; EVE economists publish quarterly economy reports.
- Run the read-only harness on a live snapshot (anonymised) and the simulator.
- Required output table, before vs after, for four archetypes: new player, median, whale, AI nation. Columns: net income per MI-hour, time to afford X, war cost per unit of damage, share of nations with net <= 0.
- **Guardrails (numeric, set once per pillar):** e.g. share of active nations with net <= 0 must not exceed today's by more than N points; new-player time-to-first-upgrade must not worsen; no archetype may profit from a sell-back loop.
- CI runs the committed fixture version of this (the existing prod-shaped CI gate).
- **Fail:** any guardrail breached = revise numbers or design. Never "ship and watch".

### G4: Review and playtest (Design review, alpha)
Studio practice: peer design review; internal alpha; a public test realm (Blizzard PTR, Paradox open-beta branch).
- **Peer review:** a second reviewer (another agent or Dede) reads the G1 doc and the G2/G3 output, not just the diff. They sign the class C/D checklist.
- **Test realm:** a copy of production with a snapshot of real data where players can try the change for 24 to 72 hours before it goes live. This does not exist yet; building it is the highest-value infrastructure item (see section 6).
- **Interim until a realm exists:** announce class D designs publicly with a feedback window, and run the change on a small cohort behind a flag (G5).
- **Player advisory group:** a small named group (for example Josh, Kaiser, Chel, Silent) gets class D designs early and is asked to break them. EVE's Council of Stellar Management and Paradox beta testers work this way. Turn the loudest critics into the best testers.
- **Fail:** unresolved exploit found in playtest = back to G2.

### G5: Build and staged rollout (Release engineering)
Studio practice: feature flags, canary releases, kill switches, grace periods.
- Branch, PR, CI green, `ano-ship` flow; schema changes and migrations checked against prod-shaped schema.
- **Feature flag** for every class C/D change with an economic effect.
- **Staged rollout:** 5 to 10% of nations (or AI nations only) for one or two ticks, observe, then all.
- **Grace period:** new costs or upkeep start after a stated delay and ramp in, never mid-tick without warning.
- **Never ship at the same moment as another economy change** (Pop 2.0 and the distribution fix landing together made the cause unreadable).
- **Rollback trigger written before shipping:** specific number and time, for example "if more than X% of nations have net <= 0 after the first tick, revert". Revert is a flag flip or a prepared revert PR, not a redesign under pressure.

### G6: Door test and live verification (QA, certification)
- The existing 6-point door test, live in Chrome as account 16 (new and old player, 390px mobile).
- **First-tick observation:** record real before and after numbers from the actual tick, compared to the G3 prediction. A mismatch beyond tolerance triggers the rollback trigger.
- Check ledger, auth and validation on every new mutating route.

### G7: Communication (Live-ops, patch notes)
Studio practice: patch notes with reasons, dev blogs, known-issues list.
- Patch note per change in plain language: what changed, why, what we measured, what we will watch.
- Post class D designs *before* shipping (G4) and results *after* (G8). The complaint that changes "ship instantly from one person's input" is answered by the visible process, not by promises.
- Wiki and wiki bot updated in the same change so docs match code 1:1.
- Name the release channel honestly: "live, actively balanced" instead of "beta", or a real separate test realm.
- Reply in the player's thread when their report ships (the existing ano-sweep voice rules).

### G8: Post-release review (Post-mortem, live-ops retro)
Studio practice: blameless post-mortem; balance changelog; KPI review at 24h, 72h, 7d.
- **24h, 72h, 7d check:** compare metric to target from G0. Record result.
- **Retro for any revert, hotfix, or class D:** what did we claim, what happened, which gate failed to catch it. Update the gate checklists, not just the code.
- **Change log of record:** one table of all economy changes with date, class, metric, outcome. This is also the answer to "every update made things worse": the log shows whether that's true.
- Close the backlog item only when the metric is met or the change is reverted.

## 4. Roles (so decisions aren't one person's call)

| Role | Who | Responsibility |
|---|---|---|
| Decision owner | Dede | Signs class D; owns pillars; no guard code needed, change designs so they don't trip it |
| Designer / builder | Claude session | G0 to G3, G5 |
| Reviewer | Second agent or Dede | G4 sign-off; reads the doc, not the diff |
| Advisory group | A few active players | G4 playtest, try to break it |
| Verifier | Claude session as account 16 | G6 |

## 5. Cadence

- **Friday:** vote items and class C/D announcements go out; the vote is an input to G0, not an auto-approval.
- **Soak:** class D changes wait at least 48h after announcement and at least one full economy cycle before the next economy change.
- **One economy change at a time.** A queue, not a pile.
- **Freeze rule:** after a revert, no new economy change for 72h so numbers settle.

## 6. Tooling that supports the gates

| Gate | Tool | Where | Status |
|---|---|---|---|
| G1 | Design doc template | `docs/templates/DESIGN_DOC_TEMPLATE.md` | Available |
| G2 | Exploit checklist | `docs/templates/EXPLOIT_CHECKLIST.md` | Available |
| G6 | Door test | `CLAUDE.md` section "Door test" | Available |
| G8 | Economy change log | `docs/ECONOMY_CHANGELOG.md` | Available |
| G5 | Feature flags and kill switch | `app_core/feature_flags.py`, admin page `/admin/flags` | Available |
| G3 | Balance harness and guardrails | `balance/` (`python -m balance.report`) | Available |
| G3 | Guardrail dashboard | admin page `/admin/guardrails` | Available |
| G4 | Test realm | `docs/TEST_REALM.md` | Scripts first; provisioning needs a cost decision from Dede |

Update the Status column in the PR that ships each tool.

## 7. Open design debts the pipeline should absorb first

Surrender rules, ally-join timing, MDP range, special weapons supply and morale, iron dome cap, standing-military score refund, upkeep v3 (derived from income per the balance spec), war ranges (population-based), small-beats-big strategy.

## 8. Rules for AI sessions

1. Before changing any cost, rate, cap, upkeep, income, tax, fee, loot or war-range value, name the class (A to D) and follow its gates.
2. Never state a game rule to a player without a code reference. If unsure, say so and check.
3. Class C and D economy changes ship behind a feature flag. Write the rollback trigger in the PR description.
4. Add a row to `docs/ECONOMY_CHANGELOG.md` in the same PR. Fill in the outcome at 24h, 72h and 7d.
5. Anything that moves a signed pillar goes to Dede first.
