# Game formulas reference (Affairs & Order)

Every rule here is copied verbatim from code with `path:line`. Verify with `python3 tools/verify_formulas.py`. Conventions: `CONFLICT:` two places disagree; `UNCLEAR:` code not decisive; `STALE COMMENT:` comment contradicts code; DB-dynamic values name the table/column. Computed examples are real script output.

Files (docs/formulas/): economy-taxes-revenue, population, food-rations, energy, resources-production, buildings-costs, military-units, military-upkeep, war-combat, war-range-targeting, finance-misc.

Key facts: war range = population/1000 x0.75..1.33 (not influence). Live tick order: :00 tax, :15 disasters, :25 revenue/upkeep, :35 unit stockpiles, :40 loan interest, :45 population, :50 war expiry.

Not covered (not read): influence_formula.py, coalitions, market routes, loans/bonds/currency services, disasters, bots/AI, tutorial/onboarding, happiness events, spy ops, strategic airstrike/drone/cruise numbers, template-vs-code number diffs.
