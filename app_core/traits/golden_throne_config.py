"""Every tunable number for "The Golden Throne" lives here (and only here).

Conservative on purpose: the owner's nation is hidden from rankings and untargetable, the
bonuses are small, and the hive trade-offs cost real food and upkeep.
"""
from datetime import time
from zoneinfo import ZoneInfo

SERVER_TZ = ZoneInfo("Europe/Vilnius")
DAWN_TIME = time(6, 0)  # fixed so the countdown is predictable

# --- Sacrifice -------------------------------------------------------------------------
SACRIFICE_SOULS = 10          # lore number; pilgrims offset it first
MIN_POPULATION_FOR_SACRIFICE = 100_000  # below this the sacrifice is skipped

# --- Vitality ---------------------------------------------------------------------------
START_VITALITY = 60.0
DEVOUR = 4.0                  # drained every dawn
SACRIFICE_RESTORE = 3.0       # restored when the full sacrifice is made
PILGRIM_RESTORE_EACH = 0.5    # per pilgrim weight (capped below)
PILGRIM_RESTORE_CAP_WEIGHT = 10
SKIP_EXTRA_PENALTY = 3.0      # on top of DEVOUR when the sacrifice is skipped
CRISIS_ENTER_AT = 0.0
CRISIS_EXIT_AT = 20.0
CRISIS_RECOVERY = 3.0         # per dawn while in crisis (decay paused)

# (min_vitality, key, label, happiness_pct, defense_pct, food_pct)
TIERS = (
    (80, "blazing", "Blazing", 3.0, 5.0, 0.0),
    (40, "steady", "Steady", 1.0, 2.0, 0.0),
    (15, "flickering", "Flickering", -2.0, 0.0, 0.0),
    (0.01, "failing", "Failing", -5.0, -5.0, -5.0),
)
CRISIS_TIER = ("crisis", "The Emperor's Light Fails", -10.0, -10.0, 0.0)

WARNINGS = {
    "blazing": "The Golden Light burns bright over Holy Terra.",
    "steady": "The Throne endures.",
    "flickering": "The Throne flickers... the faithful are urged to make pilgrimage.",
    "failing": "The Golden Light gutters. Hive-priests whisper of the end.",
    "crisis": "The Emperor's Light Fails. Unrest spreads through the hive.",
}

# --- Pilgrims ---------------------------------------------------------------------------
PILGRIM_COST_POPULATION = 1_000
PILGRIM_MIN_ACCOUNT_AGE_DAYS = 2
PILGRIM_BLESSING_PCT = 2.0     # happiness points
PILGRIM_BLESSING_HOURS = 24
SURGE_MULTIPLIER = 2

# --- Hive City (permanent modifiers) ----------------------------------------------------
HIVE_POP_CAP_MULT = 1.25
HIVE_INDUSTRY_MULT = 1.10
HIVE_FOOD_MULT = 0.75
HIVE_UPKEEP_MULT = 1.15

# --- Throne events ----------------------------------------------------------------------
EVENT_CHANCE_PER_DAWN = 1 / 7
EVENT_MIN_GAP_DAYS = 5
EVENT_DURATION_HOURS = 24
EVENTS = {
    "whispers": {"label": "Whispers from the Throne", "weight": 1},
    "heretics": {"label": "Heretic Uprising", "weight": 1},
    "surge": {"label": "Pilgrim Surge", "weight": 1},
}
WHISPERS_CHOICES = (
    {"kind": "happiness", "pct": 2.0, "text": "A calm settles over the hive (+2% happiness)."},
    {"kind": "industry", "mult": 1.05, "text": "The forges sing (+5% industry output)."},
    {"kind": "vitality", "amount": 3.0, "text": "A golden pulse runs through the Throne (+3 vitality)."},
)
HERETIC_HAPPINESS_PCT = -5.0
HERETIC_VITALITY_LOSS = 3.0

# --- Wall of the Spent ------------------------------------------------------------------
WALL_PAGE_SIZE = 40
