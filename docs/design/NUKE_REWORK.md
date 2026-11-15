# Design: Nuclear rework (class D, flag `nuke_rework`, ships OFF)

Source: Discord #suggestions "Changes/additions to nuke mechanics" (thread 1563719318448115773), passed 8 yes / 0 no, 2026-11-06. Dede: "you make it balanced".

## 0. Problem and metric
Nukes today are one warhead per war (wars/nuclear.py, wars.rules.MAX_NUKE_VOLLEYS_PER_WAR = 1), bought outright for 80M gold + resources up to one per silo (attack_scripts/Nations.py: `nukes = max(0, silos - owned)`). Players asked for nukes to be a long-term, capacity-limited investment whose use is a one-shot commitment that hurts both sides, with retaliation and a real political cost.
Success metrics (checked in the test realm before the flag flips): (a) time to a 10-missile arsenal from zero >= 6 days with 5 facilities; (b) total arsenal cost of 10 missiles >= 3x today's price; (c) a first-strike salvo never removes more than the caps below; (d) no path to nukes without a facility.

## 1. Facts from code
| Fact | Where |
|---|---|
| Silo costs 350M gold + 1.08M steel + 480k alu, upkeep 340k/h | variables.py `silos_price`, `silos_money` |
| Nuke costs 80M gold + 120k alu + 100k comp + 25k gas + 20k uranium | variables.py MILDICT `nukes` |
| Stockpile pattern: building makes unit into `user_unit_stockpile`, player activates for gold | app_core/game_ticks/unit_production.py, military/services.py `process_activate_units` |
| harbours = naval bases, aerodomes = air bases | variables.py |
| One volley per war per side, influence cost 50% first / 25% retaliation, decays 7 days | wars/nuclear.py, influence_formula.py |
| Iron Dome roll per warhead (nukes 50% cap) | app_core/military/iron_dome.py, wars/air_defense.py |
| Star Wars Project exists (+25% interception) | iron_dome.has_star_wars |

## 2. Rules (flag ON)
1. **Capacity.** Armed missiles <= silos x 1. Armed subs <= floor(harbours / 25). Armed bombers <= floor(aerodomes / 25). Silos/bases never produce anything.
2. **Nuclear Weapons Facility** (land building). Only source of armed units. Price 500M gold + 1.5M steel + 700k alu + 400k components + 200k uranium; upkeep 500k gold/h (more than a silo). 1 facility = progress toward each unit type at: missile 1 per 72h, submarine 1 per 120h, bomber 1 per 96h (shared: a facility works on one type at a time, set per facility owner via a "focus" selector). Production stops at capacity (stockpile + owned >= capacity) and when resources are short.
3. **Per-unit resources at production:** missile = existing nuke resources (120k alu, 100k comp, 25k gas, 20k uranium); submarine = 1.5M steel, 250k comp, 60k uranium, 60k gas; bomber = 700k alu, 200k comp, 50k uranium, 50k gas.
4. **Activation** (stockpile -> arsenal) costs gold: missile 80M (today's price), submarine 400M, bomber 300M. Manual by default so nothing is bought against your will; per-unit **auto-activate** toggle buys each unit the tick it is produced if you can afford it, otherwise it waits in stockpile. Stockpile units are not usable in war and not counted by upkeep.
5. **Upkeep:** armed units cost gasoline per hour like other strategic units: missile 400, submarine 1,500, bomber 1,200 (silo+missile pair costs less than sub/bomber, as requested).
6. **Fire All** (replaces single launches; old path stays when flag off): once per war per side (existing volley flag). Launches every armed missile, submarine and bomber at the chosen opponent. Warheads are spread over the enemy provinces, most populated first, one each, then wrapping; repeat hits use the existing halving. Each warhead rolls Iron Dome in the province it hits.
7. **Salvo destruction caps (initial salvo):** silos + armed missiles lose at most 50%; harbours/aerodomes + armed subs/bombers lose at most 20% (counts taken before impact; extra destruction of those types is skipped).
8. **Retaliation.** Per-nation toggle "auto-retaliate". When a salvo is launched at you with it ON, detection coverage D (25% base, +25% with the Star Wars Project) of your armed arsenal fires back immediately, from the pre-impact arsenal; the rest fires after the cap-limited losses. Counts as your one volley; you do not need influence to retaliate. Uses the same Fire All resolution.
9. **Political penalty.** Replaces the 50%/25% compounding cost with a flat 75% influence cut for the attacker (retaliation 40%), decaying linearly over 7 days (existing machinery).
10. **Direct purchase of `nukes` is closed** while the flag is on (existing owned nukes stay and count against silo capacity).
Deferred (not in this change): espionage "sabotage facility" and a dedicated detection building. Tracked in the backlog.

## 3. Balance reasoning
- Cost: missile arsenal of 10 needs 10 silos (3.5B gold) + facilities (>= 2.5B) + 10 x 80M activation + resources: >= 3x today's cost of the same 10 nukes (800M + silos).
- Time: 1 missile per 72h per facility => 5 facilities give 1.67 missiles/day, 10 in 6 days. Subs/bombers need 25 bases per unit, so a single bomber means 25 aerodomes (550M gold).
- Retaliation + caps give mutual destruction without first-strike disarm: at most 50% / 20% lost on impact, then the defender fires back the detected share at once.
- Penalty 75% flat is meant to cut the user off from WA for days, as asked.
- Snowball check: nukes only exist as a slow, expensive late-game sink; they do not feed income.

## 4. Exploit review (docs/templates/EXPLOIT_CHECKLIST.md)
- Free units: production spends resources via ledger; activation spends gold via ledger; both under the user advisory lock; stockpile has CHECK quantity >= 0.
- Sell-back loop: nukes cannot be sold for refund while flag on (sell route blocked for armed units); stockpile cannot be sold.
- Alt-account feeding: units are not transferable; no new gift path.
- Double submit / race: Fire All runs under the attacker's advisory lock and flips the volley flag first; retaliation flips the defender's flag under the defender's lock taken in id order (no deadlock).
- Capacity gaming (build silos, activate, sell silos): activation checks capacity only at activation; a periodic cap check destroys armed units above capacity at the next tick (no free overflow).
- War-less use: Fire All only inside an active war the user belongs to; vacation/untargetable nations excluded by existing blocks_interaction.
- Negative/huge numbers: no player-supplied quantities except province choice and toggles.

## 5. Rollout and rollback
Ships OFF (migration inserts flag disabled). Test in the realm first (docs/TEST_REALM.md), then Dede flips for everyone. Rollback trigger: a salvo that exceeds the caps, an unbuildable facility, or tick errors in nuke_production -> flag off restores the old single-nuke path; facilities/units already made stay but are inert.
Announcement and tutorial text updated in the same PR set; ECONOMY_CHANGELOG row per phase.
