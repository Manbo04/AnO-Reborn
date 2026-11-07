# Loans, bonds, currency, market fees (constants only)

### Loans
**Exact rule** (verbatim) - **Source:** `variables.py:1237-1256`
```python
LOAN_CAP_PER_POPULATION = 40  # $ of borrowing capacity per population point
LOAN_MIN_AMOUNT = 100_000
LOAN_ORIGINATION_FEE = 0.10  # one-time fee added to principal at issuance
LOAN_HIGH_UTILIZATION_THRESHOLD = 0.70  # fraction of borrowing cap
LOAN_HIGH_UTILIZATION_FEE = 0.20  # fee on ONLY the part of a loan above the threshold (rest pays LOAN_ORIGINATION_FEE)
LOAN_COOLDOWN_HOURS = 24  # can't take a new loan until this long after fully repaying the last one

# Loan credit score (Kurai, #suggestions 2026-09-07): repaying on time raises
# the borrowing cap a little, paying late / sitting in default lowers it.
# Scored over the nation's last LOAN_CREDIT_WINDOW loans, see
# app_core/loans/services.py::score_loan_history. Points are percent of cap.
LOAN_TERM_DAYS = 7  # a loan repaid within this many days counts as "on time"
LOAN_DEFAULT_DAYS = 21  # outstanding longer than this = in default
LOAN_CREDIT_WINDOW = 10  # only the most recent N loans count
LOAN_CREDIT_ON_TIME_POINTS = 5  # per full-size on-time loan
LOAN_CREDIT_FULL_SIZE_SHARE = 0.25  # loan must be >= 25% of cap to earn full on-time points
LOAN_CREDIT_LATE_POINTS = -5  # repaid after LOAN_TERM_DAYS, or currently overdue
LOAN_CREDIT_DEFAULT_REPAID_POINTS = -10  # repaid only after LOAN_DEFAULT_DAYS
LOAN_CREDIT_IN_DEFAULT_POINTS = -15  # still outstanding past LOAN_DEFAULT_DAYS
LOAN_CREDIT_MAX_POINTS = 25  # cap multiplier bounded to [0.75, 1.25]
```
**Notes:** only the constants were read; the services in app_core/loans were not.

### Bonds and currency unions
**Exact rule** (verbatim) - **Source:** `variables.py:1266-1288`
```python
BOND_CAP_PER_POPULATION = 30  # $ of total outstanding (listed+active) bond principal per population point

# Market / trade fees (app_core/market/fees.py). Charged to whoever completes
# a money trade (buying from a sell offer, filling a buy offer, accepting a
# direct trade) on top of / out of the traded amount, and removed from the
# economy -- simulates transport costs.
TRADE_FEE_PERCENT = 5
# Reduced fee between two members of the same currency union.
UNION_TRADE_FEE_PERCENT = 2

# Currency unions (app_core/currency_unions). Benefits only apply while the
# union has at least CURRENCY_UNION_MIN_MEMBERS members.
CURRENCY_UNION_MIN_MEMBERS = 2
CURRENCY_UNION_BOND_CAP_MULTIPLIER = 1.25  # +25% bond issuance cap
CURRENCY_UNION_NAME_MAX = 60
CURRENCY_UNION_CURRENCY_MAX = 40
BOND_MIN_PRINCIPAL = 50_000
BOND_MIN_INTEREST_RATE = 0.001  # 0.1%/day
BOND_MAX_INTEREST_RATE = 0.02   # 2%/day
BOND_MIN_TERM_DAYS = 3
BOND_MAX_TERM_DAYS = 30
BOND_MAX_DEFAULT_STRIKES = 3    # missed daily interest payments before a bond is force-defaulted early instead of waiting for maturity
BOND_DEFAULT_COOLDOWN_DAYS = 14  # can't issue a new bond this long after defaulting on one
```
### National currency
**Exact rule** (verbatim) - **Source:** `variables.py:1298`
```python
CURRENCY_GOLD_PER_UNIT = 5  # gold cost to mint 1 unit of national currency; same rate redeems it back
```
### Market trade fee
**Exact rule** (verbatim) - **Source:** `variables.py:1272-1274`
```python
TRADE_FEE_PERCENT = 5
# Reduced fee between two members of the same currency union.
UNION_TRADE_FEE_PERCENT = 2
```
**Exact rule** (verbatim) - **Source:** `app_core/market/fees.py:18-19`
```python
        return variables.UNION_TRADE_FEE_PERCENT
    return variables.TRADE_FEE_PERCENT
```
**Used by (grep):** `TRADE_FEE_PERCENT` -> `app.py:37`, `app.py:912`, `app_core/currency_unions/services.py:160`, `app_core/market/fees.py:19`, `app_core/market/auto_order_routes.py:70`, `app_core/market/routes.py:68`; `UNION_TRADE_FEE_PERCENT` -> `app.py:37`, `app.py:913`, `app_core/currency_unions/services.py:161`, `app_core/market/fees.py:18`, `app_core/market/routes.py:66`

### Policies (IDs and effects)
**Exact rule** (verbatim) - **Source:** `variables.py:316-358`
```python
# POLICY DEFINITIONS
# Policy IDs (stored as integers in user's policy arrays)
POLICY_UNIVERSAL_HEALTHCARE = 1
POLICY_MANDATORY_SCHOOLING = 2
POLICY_INDUSTRIAL_SUBSIDIES = 3
POLICY_RATIONING_PROGRAM = 4

# Policy effect multipliers
POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER = 1.2  # +20% elderly CG consumption
POLICY_HEALTHCARE_ELDERLY_DEATH_REDUCTION = 0.7  # -30% elderly death rate
POLICY_HEALTHCARE_HAPPINESS_BONUS = 5  # +5 happiness per province

POLICY_SCHOOLING_GRADUATION_MULTIPLIER = 1.5  # +50% graduation rates
POLICY_SCHOOLING_HAPPINESS_BONUS = 3  # +3 happiness (educated populace)

POLICY_SUBSIDIES_UPKEEP_REDUCTION = 0.7  # -30% upkeep for industrial buildings
POLICY_SUBSIDIES_POLLUTION_MULTIPLIER = 1.3  # +30% pollution from industry
# Per templates/mechanics.html, this policy is documented to affect
# "Industrial Districts, Factories, Steel Mills, Power Plants" -- i.e. every
# building in the "electricity" category (INFRA_TYPE_BUILDINGS["electricity"])
# and both *_factories buildings, not just coal/oil burners and
# component_factories. Previously only 2 of the 7 power plant types (and 1 of
# the 2 factory types) were listed, so nations running on hydro/nuclear/solar/
# wind/geothermal power (a very common late-game choice, since those are the
# only power plants with zero pollution to begin with) saw no upkeep discount
# at all from this policy -- matching the player report that expenses never
# actually went down.
POLICY_SUBSIDIES_AFFECTED_BUILDINGS = [
    "industrial_district",
    "component_factories",
    "ammunition_factories",
    "steel_mills",
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "wind_farms",
    "geothermal_plants",
]

POLICY_RATIONING_CONSUMPTION_REDUCTION = 0.85  # -15% rations consumption
POLICY_RATIONING_HAPPINESS_PENALTY = 10  # -10 happiness per province
```
**Notes:** CONFLICT: hidden extra effects of policy IDs 1, 2, 3 and 6 are in building-costs and economy files (building_costs.py:151-160, province_effects.py:46-48). Country page text (templates/country.html, "National Policies") lists policies 1,2,3,4,6 with no mention of those effects.

### Upgrades keyed names with code effects
**Exact rule** (verbatim) - **Source:** `app_core/economy/project_bonuses.py:23-27`
```python
PROJECT_OUTPUT_BONUSES: dict[str, tuple[str, float]] = {
    "bauxite_mines": ("strongerexplosives", 0.45),
    "farms": ("advancedmachinery", 0.5),
    "steel_mills": ("integratedsteelmaking", 0.36),
}
```
**Notes:** tech cost is DB (`tech_dictionary.research_cost`), paid in `components` (action_loop.py:13, 285). Late techs need 2 universities (action_loop.py:259-277). `lootingteams` +10 pts on spoils (war_orchestrator.py:244), others in economy files. `organizedsupplylines`, `largestorehouses`: no code effect found by grep.

## Not covered
Influence score, coalitions, market routes, loans/bonds services, disasters, bots/AI, tutorial/onboarding, happiness beyond the revenue tick.
