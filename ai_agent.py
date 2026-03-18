"""
AI Nation Agent for Affairs & Order
====================================
Plays the game legitimately via HTTP requests - no DB cheating.
Runs every game tick (hourly) as a Celery task.

Strategy priorities (balanced):
  1. Fix critical deficits (energy, food, distribution)
  2. Grow economy (resource extraction → processing → consumer goods)
  3. Maintain happiness (public works, pollution control)
  4. Build military (proportional to economy size)
  5. Expand (buy provinces/land/cities when affordable)
"""

import os
import json
import time
import logging
import math
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ai_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] AI-Agent %(levelname)s: %(message)s")
    )
    logger.addHandler(handler)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("AI_AGENT_BASE_URL", "https://affairsandorder.com")
AI_USER_ID = int(os.getenv("AI_AGENT_USER_ID", "1"))  # Dede
AI_USERNAME = os.getenv("AI_AGENT_USERNAME", "Dede")
AI_PASSWORD = os.getenv("AI_AGENT_PASSWORD", "")

# How much gold to keep as reserve (never spend below this)
GOLD_RESERVE = int(os.getenv("AI_GOLD_RESERVE", "5000000"))  # 5M default

# Max buildings to buy per tick per type (prevent blowing all gold at once)
MAX_BUILD_PER_TICK = int(os.getenv("AI_MAX_BUILD_PER_TICK", "3"))

# Max military units to buy per tick per type
MAX_MILITARY_PER_TICK = int(os.getenv("AI_MAX_MILITARY_PER_TICK", "50"))

# ---------------------------------------------------------------------------
# Game constants (mirrored from variables.py)
# ---------------------------------------------------------------------------
RESOURCES = [
    "rations",
    "oil",
    "coal",
    "uranium",
    "bauxite",
    "lead",
    "copper",
    "iron",
    "lumber",
    "components",
    "steel",
    "consumer_goods",
    "aluminium",
    "gasoline",
    "ammunition",
]

ENERGY_BUILDINGS = [
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
]

# Building name → what it produces and consumes per tick
NEW_INFRA = {
    "coal_burners": {
        "plus": {"energy": 4},
        "minus": {"coal": 11},
        "money": 7800,
        "eff": {"pollution": 6},
    },
    "oil_burners": {
        "plus": {"energy": 5},
        "minus": {"oil": 16},
        "money": 11700,
        "eff": {"pollution": 4},
    },
    "hydro_dams": {"plus": {"energy": 6}, "money": 24000},
    "nuclear_reactors": {
        "plus": {"energy": 15},
        "minus": {"uranium": 32},
        "money": 111000,
    },
    "solar_fields": {"plus": {"energy": 3}, "money": 13000},
    "distribution_centers": {"plus": {"consumer_goods": 8}, "money": 15000},
    "gas_stations": {
        "plus": {"consumer_goods": 12},
        "eff": {"pollution": 4},
        "money": 20000,
    },
    "general_stores": {
        "plus": {"consumer_goods": 10},
        "eff": {"pollution": 2},
        "money": 37500,
    },
    "farmers_markets": {
        "plus": {"consumer_goods": 16},
        "eff": {"pollution": 5},
        "money": 80000,
    },
    "banks": {"plus": {"consumer_goods": 20}, "money": 220000},
    "malls": {"plus": {"consumer_goods": 30}, "eff": {"pollution": 9}, "money": 450000},
    "industrial_district": {
        "plus": {"consumer_goods": 50},
        "eff": {"pollution": 15},
        "money": 85000,
    },
    "city_parks": {
        "eff": {"happiness": 5},
        "effminus": {"pollution": 6},
        "money": 25000,
    },
    "libraries": {"eff": {"happiness": 5, "productivity": 3}, "money": 60000},
    "hospitals": {"eff": {"happiness": 8}, "money": 85000},
    "universities": {"eff": {"productivity": 10, "happiness": 4}, "money": 175000},
    "primary_school": {"eff": {"productivity": 2, "happiness": 2}, "money": 30000},
    "high_school": {"eff": {"productivity": 5, "happiness": 3}, "money": 75000},
    "monorails": {
        "eff": {"productivity": 16},
        "effminus": {"pollution": 20},
        "money": 270000,
    },
    "army_bases": {"money": 25000},
    "harbours": {"money": 35000},
    "aerodomes": {"money": 55000},
    "admin_buildings": {"money": 90000},
    "silos": {"money": 340000},
    "farms": {"money": 3000, "plus": {"rations": 12}, "eff": {"pollution": 1}},
    "pumpjacks": {"money": 9500, "plus": {"oil": 24}, "eff": {"pollution": 2}},
    "coal_mines": {"money": 4200, "plus": {"coal": 31}, "eff": {"pollution": 2}},
    "bauxite_mines": {"money": 8000, "plus": {"bauxite": 20}, "eff": {"pollution": 2}},
    "copper_mines": {"money": 5000, "plus": {"copper": 25}, "eff": {"pollution": 2}},
    "uranium_mines": {"money": 45000, "plus": {"uranium": 12}, "eff": {"pollution": 1}},
    "lead_mines": {"money": 7200, "plus": {"lead": 19}, "eff": {"pollution": 2}},
    "iron_mines": {"money": 11000, "plus": {"iron": 23}, "eff": {"pollution": 2}},
    "lumber_mills": {"money": 7500, "plus": {"lumber": 35}, "eff": {"pollution": 1}},
    "component_factories": {
        "money": 50000,
        "minus": {"copper": 20, "steel": 10, "aluminium": 15},
        "plus": {"components": 5},
        "eff": {"pollution": 5},
    },
    "steel_mills": {
        "money": 60000,
        "minus": {"coal": 35, "iron": 35},
        "plus": {"steel": 12},
        "eff": {"pollution": 4},
    },
    "ammunition_factories": {
        "money": 15000,
        "minus": {"copper": 10, "lead": 20},
        "plus": {"ammunition": 12},
        "eff": {"pollution": 3},
    },
    "aluminium_refineries": {
        "money": 42000,
        "minus": {"bauxite": 15},
        "plus": {"aluminium": 16},
        "eff": {"pollution": 3},
    },
    "oil_refineries": {
        "money": 35000,
        "minus": {"oil": 20},
        "plus": {"gasoline": 11},
        "eff": {"pollution": 6},
    },
}

# Building gold cost
BUILDING_COSTS = {
    "coal_burners": 2500000,
    "oil_burners": 4500000,
    "hydro_dams": 35000000,
    "nuclear_reactors": 150000000,
    "solar_fields": 8000000,
    "gas_stations": 7000000,
    "general_stores": 15000000,
    "farmers_markets": 4500000,
    "malls": 225000000,
    "banks": 120000000,
    "industrial_district": 280000000,
    "distribution_centers": 5000000,
    "city_parks": 4500000,
    "hospitals": 30000000,
    "libraries": 10000000,
    "universities": 40000000,
    "monorails": 250000000,
    "primary_school": 4000000,
    "high_school": 12000000,
    "army_bases": 8000000,
    "harbours": 18000000,
    "aerodomes": 22000000,
    "admin_buildings": 50000000,
    "silos": 350000000,
    "farms": 1500000,
    "pumpjacks": 3000000,
    "coal_mines": 3500000,
    "bauxite_mines": 3200000,
    "copper_mines": 2800000,
    "uranium_mines": 5500000,
    "lead_mines": 2600000,
    "iron_mines": 3800000,
    "lumber_mills": 2200000,
    "component_factories": 16000000,
    "steel_mills": 12000000,
    "ammunition_factories": 10000000,
    "aluminium_refineries": 11000000,
    "oil_refineries": 9000000,
}

# Building resource cost
BUILDING_RESOURCE_COSTS = {
    "coal_burners": {"lumber": 40000},
    "oil_burners": {"lumber": 60000, "iron": 20000},
    "hydro_dams": {"steel": 180000, "aluminium": 90000},
    "nuclear_reactors": {"steel": 500000},
    "solar_fields": {"copper": 40000, "bauxite": 30000},
    "gas_stations": {"steel": 75000, "aluminium": 50000},
    "general_stores": {"steel": 90000, "aluminium": 105000},
    "farmers_markets": {"steel": 110000, "aluminium": 120000},
    "malls": {"steel": 540000, "aluminium": 360000},
    "banks": {"steel": 340000, "aluminium": 165000},
    "industrial_district": {"steel": 800000, "components": 200000},
    "distribution_centers": {"lumber": 50000, "iron": 20000},
    "city_parks": {"steel": 22000},
    "hospitals": {"steel": 210000, "aluminium": 130000},
    "libraries": {"steel": 85000, "aluminium": 60000},
    "universities": {"steel": 150000, "aluminium": 80000},
    "monorails": {"steel": 600000, "aluminium": 300000},
    "primary_school": {"steel": 25000, "aluminium": 15000},
    "high_school": {"steel": 60000, "aluminium": 40000},
    "army_bases": {"lumber": 120000},
    "harbours": {"steel": 320000},
    "aerodomes": {"aluminium": 60000, "steel": 250000},
    "admin_buildings": {"steel": 135000, "aluminium": 110000},
    "silos": {"steel": 1080000, "aluminium": 480000},
    "farms": {"lumber": 15000},
    "pumpjacks": {"iron": 22000},
    "coal_mines": {"lumber": 45000},
    "bauxite_mines": {"lumber": 30000},
    "copper_mines": {"lumber": 38000},
    "uranium_mines": {"iron": 35000, "lumber": 25000},
    "lead_mines": {"lumber": 38000},
    "iron_mines": {"lumber": 30000},
    "lumber_mills": {},
    "component_factories": {"steel": 30000, "aluminium": 30000},
    "steel_mills": {"iron": 60000, "coal": 40000, "lumber": 30000},
    "ammunition_factories": {"iron": 25000, "copper": 15000},
    "aluminium_refineries": {"iron": 40000, "lumber": 20000},
    "oil_refineries": {"iron": 30000, "lumber": 15000},
}

# Military unit costs
MILDICT = {
    "soldiers": {"price": 250, "resources": {"rations": 500}, "manpower": 1},
    "tanks": {
        "price": 7000,
        "resources": {"components": 5000, "steel": 50000, "gasoline": 2000},
        "manpower": 4,
    },
    "artillery": {
        "price": 14000,
        "resources": {"components": 3000, "steel": 30000, "gasoline": 1000},
        "manpower": 2,
    },
    "bombers": {
        "price": 22000,
        "resources": {"components": 15000, "steel": 25000, "gasoline": 8000},
        "manpower": 1,
    },
    "fighters": {
        "price": 30000,
        "resources": {"components": 10000, "steel": 20000, "gasoline": 5000},
        "manpower": 1,
    },
    "apaches": {
        "price": 28000,
        "resources": {"components": 8000, "steel": 15000, "gasoline": 3000},
        "manpower": 1,
    },
    "destroyers": {
        "price": 26000,
        "resources": {"rations": 500, "components": 400, "steel": 300, "gasoline": 100},
        "manpower": 6,
    },
    "cruisers": {
        "price": 48000,
        "resources": {"rations": 600, "components": 500, "steel": 400, "gasoline": 150},
        "manpower": 5,
    },
    "submarines": {
        "price": 40000,
        "resources": {"rations": 700, "components": 600, "steel": 500, "gasoline": 200},
        "manpower": 6,
    },
    "spies": {
        "price": 25000,
        "resources": {"rations": 100, "components": 200},
        "manpower": 0,
    },
}

# Slot type for buildings (city slot vs land slot)
CITY_SLOT_BUILDINGS = {
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "gas_stations",
    "general_stores",
    "farmers_markets",
    "malls",
    "banks",
    "distribution_centers",
    "city_parks",
    "hospitals",
    "libraries",
    "universities",
    "monorails",
}
LAND_SLOT_BUILDINGS = {
    "army_bases",
    "harbours",
    "aerodomes",
    "admin_buildings",
    "silos",
    "farms",
    "pumpjacks",
    "coal_mines",
    "bauxite_mines",
    "copper_mines",
    "uranium_mines",
    "lead_mines",
    "iron_mines",
    "lumber_mills",
    "component_factories",
    "steel_mills",
    "ammunition_factories",
    "aluminium_refineries",
    "oil_refineries",
}


# ---------------------------------------------------------------------------
# Game State Reader (reads from DB — read-only, no modifications)
# ---------------------------------------------------------------------------
class GameState:
    """Reads all relevant game state for a user from the production database."""

    def __init__(self, user_id):
        self.user_id = user_id
        self.gold = 0
        self.manpower = 0
        self.provinces = []  # list of dicts with id, name, land, cityCount, pop, etc.
        self.buildings = {}  # {province_id: {building_name: count}}
        self.total_buildings = {}  # {building_name: total_count} across all provinces
        self.resources = {}  # {resource_name: quantity}
        self.military = {}  # {unit_name: count}
        self.happiness = 0
        self.pollution = 0
        self.population = 0  # total across all provinces
        self.pop_working = 0
        self.pop_children = 0
        self.pop_elderly = 0
        self.energy_production = 0
        self.energy_consumption = 0
        self.building_id_map = {}  # {building_name: building_id}
        self.province_count = 0

    def load(self):
        """Load full game state from DB (read-only)."""
        import psycopg2
        from psycopg2.extras import RealDictCursor

        db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("No DATABASE_PUBLIC_URL or DATABASE_URL configured")

        conn = psycopg2.connect(db_url)
        conn.set_session(readonly=True, autocommit=True)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                self._load_gold_manpower(cur)
                self._load_provinces(cur)
                self._load_building_dict(cur)
                self._load_buildings(cur)
                self._load_resources(cur)
                self._load_military(cur)
                self._calc_energy()
        finally:
            conn.close()

        logger.info(
            "State loaded: gold=%s, provinces=%d, pop=%s, energy=%d/%d, happiness=%s",
            f"{self.gold:,.0f}",
            self.province_count,
            f"{self.population:,.0f}",
            self.energy_production,
            self.energy_consumption,
            self.happiness,
        )

    def _load_gold_manpower(self, cur):
        cur.execute("SELECT gold, manpower FROM stats WHERE id=%s", (self.user_id,))
        row = cur.fetchone()
        if row:
            self.gold = int(row["gold"] or 0)
            self.manpower = int(row["manpower"] or 0)

    def _load_provinces(self, cur):
        cur.execute(
            """SELECT id, provincename, land, citycount,
                      pop_working, pop_children, pop_elderly,
                      happiness, pollution
               FROM provinces WHERE userid=%s ORDER BY id""",
            (self.user_id,),
        )
        rows = cur.fetchall()
        # Normalize keys: map DB columns to our internal names
        self.provinces = []
        for r in rows:
            d = dict(r)
            # Map lowercase DB columns to our expected keys
            d["cityCount"] = d.pop("citycount", 0)
            d["provinceName"] = d.pop("provincename", "")
            self.provinces.append(d)
        self.province_count = len(self.provinces)
        self.population = sum(
            (p.get("pop_working") or 0)
            + (p.get("pop_children") or 0)
            + (p.get("pop_elderly") or 0)
            for p in self.provinces
        )
        self.pop_working = sum(p.get("pop_working") or 0 for p in self.provinces)
        self.pop_children = sum(p.get("pop_children") or 0 for p in self.provinces)
        self.pop_elderly = sum(p.get("pop_elderly") or 0 for p in self.provinces)
        if self.provinces:
            self.happiness = sum(p.get("happiness") or 0 for p in self.provinces) / len(
                self.provinces
            )
            self.pollution = sum(p.get("pollution") or 0 for p in self.provinces) / len(
                self.provinces
            )

    def _load_building_dict(self, cur):
        cur.execute(
            "SELECT building_id, name FROM building_dictionary WHERE is_active=TRUE"
        )
        for row in cur.fetchall():
            self.building_id_map[row["name"]] = row["building_id"]

    def _load_buildings(self, cur):
        cur.execute(
            """SELECT ub.province_id, bd.name, ub.quantity
               FROM user_buildings ub
               JOIN building_dictionary bd ON bd.building_id = ub.building_id
               WHERE ub.user_id=%s""",
            (self.user_id,),
        )
        self.total_buildings = {}
        self.buildings = {}
        for row in cur.fetchall():
            pid = row["province_id"]
            name = row["name"]
            qty = int(row["quantity"] or 0)
            if pid not in self.buildings:
                self.buildings[pid] = {}
            self.buildings[pid][name] = qty
            self.total_buildings[name] = self.total_buildings.get(name, 0) + qty

    def _load_resources(self, cur):
        cur.execute(
            """SELECT rd.name, COALESCE(ue.quantity, 0) as quantity
               FROM resource_dictionary rd
               LEFT JOIN user_economy ue
                   ON ue.resource_id = rd.resource_id AND ue.user_id=%s
               WHERE rd.is_active=TRUE""",
            (self.user_id,),
        )
        for row in cur.fetchall():
            self.resources[row["name"]] = int(row["quantity"] or 0)

    def _load_military(self, cur):
        cur.execute(
            """SELECT ud.name, COALESCE(um.quantity, 0) as quantity
               FROM unit_dictionary ud
               LEFT JOIN user_military um
                   ON um.unit_id = ud.unit_id AND um.user_id=%s
               WHERE ud.is_active=TRUE""",
            (self.user_id,),
        )
        for row in cur.fetchall():
            self.military[row["name"]] = int(row["quantity"] or 0)

    def _calc_energy(self):
        """Calculate total energy production and consumption from buildings."""
        self.energy_production = 0
        self.energy_consumption = 0
        for bname, count in self.total_buildings.items():
            info = NEW_INFRA.get(bname)
            if not info:
                continue
            plus = info.get("plus", {})
            if "energy" in plus:
                self.energy_production += plus["energy"] * count
            # Non-energy buildings that produce something consume 1 energy each
            elif plus and "energy" not in plus:
                self.energy_consumption += count

    @property
    def energy_surplus(self):
        return self.energy_production - self.energy_consumption

    @property
    def available_gold(self):
        """Gold available for spending (above reserve)."""
        return max(0, self.gold - GOLD_RESERVE)

    def get_free_city_slots(self, province):
        """Calculate free city slots for a province."""
        pid = province["id"]
        total_city = province.get("cityCount") or 0
        used = sum(self.buildings.get(pid, {}).get(b, 0) for b in CITY_SLOT_BUILDINGS)
        return max(0, total_city - used)

    def get_free_land_slots(self, province):
        """Calculate free land slots for a province."""
        pid = province["id"]
        total_land = province.get("land") or 0
        used = sum(self.buildings.get(pid, {}).get(b, 0) for b in LAND_SLOT_BUILDINGS)
        return max(0, total_land - used)

    def total_building_upkeep(self):
        """Total gold upkeep per tick from all buildings."""
        total = 0
        for bname, count in self.total_buildings.items():
            info = NEW_INFRA.get(bname)
            if info:
                total += info.get("money", 0) * count
        return total

    def resource_production_rate(self, resource_name):
        """Net production rate of a resource per tick (positive = surplus)."""
        production = 0
        consumption = 0
        for bname, count in self.total_buildings.items():
            info = NEW_INFRA.get(bname)
            if not info:
                continue
            plus = info.get("plus", {})
            minus = info.get("minus", {})
            if resource_name in plus:
                production += plus[resource_name] * count
            if resource_name in minus:
                consumption += minus[resource_name] * count
        return production - consumption


# ---------------------------------------------------------------------------
# HTTP Game Client (performs actions via legitimate HTTP requests)
# ---------------------------------------------------------------------------
class GameClient:
    """Interacts with the game via HTTP POST requests, just like a real player."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "AnO-AI-Agent/1.0",
            }
        )
        self.logged_in = False
        self.actions_taken = []

    def login(self):
        """Authenticate with the game server."""
        if not AI_PASSWORD:
            raise RuntimeError(
                "AI_AGENT_PASSWORD env var not set. "
                "Set it to Dede's account password."
            )
        resp = self.session.post(
            f"{BASE_URL}/login/",
            data={"username": AI_USERNAME, "password": AI_PASSWORD},
            allow_redirects=False,
        )
        # Successful login redirects to / (302)
        if resp.status_code in (302, 303, 200):
            self.logged_in = True
            logger.info("Logged in as %s", AI_USERNAME)
        else:
            raise RuntimeError(
                f"Login failed: status={resp.status_code}, url={resp.url}"
            )

    def _post(self, path, data=None, description=""):
        """Make a POST request to the game. Returns response."""
        if not self.logged_in:
            self.login()

        url = f"{BASE_URL}{path}"
        resp = self.session.post(url, data=data, allow_redirects=True)

        action = {
            "time": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "data": data,
            "status": resp.status_code,
            "description": description,
        }
        self.actions_taken.append(action)

        if resp.status_code >= 400:
            logger.warning("Action failed: %s → %d", description, resp.status_code)
        else:
            logger.info("Action OK: %s", description)

        return resp

    def build(self, building_name, building_id, province_id, quantity=1):
        """Build a structure in a province."""
        return self._post(
            "/build_structure",
            data={
                "building_id": str(building_id),
                "quantity": str(quantity),
                "province_id": str(province_id),
            },
            description=f"Build {quantity}x {building_name} in province {province_id}",
        )

    def buy_land(self, province_id, amount=1):
        """Buy land slots for a province."""
        return self._post(
            f"/buy/land/{province_id}",
            data={"land": str(amount)},
            description=f"Buy {amount} land in province {province_id}",
        )

    def buy_city(self, province_id, amount=1):
        """Buy city slots for a province."""
        return self._post(
            f"/buy/cityCount/{province_id}",
            data={"cityCount": str(amount)},
            description=f"Buy {amount} city slots in province {province_id}",
        )

    def buy_military(self, unit_name, quantity):
        """Buy military units."""
        return self._post(
            f"/military/buy/{unit_name}",
            data={unit_name: str(quantity)},
            description=f"Buy {quantity}x {unit_name}",
        )

    def create_province(self, name):
        """Create a new province."""
        return self._post(
            "/createprovince",
            data={"name": name},
            description=f"Create province '{name}'",
        )

    def post_sell_offer(self, resource, amount, price):
        """Post a sell offer on the market."""
        return self._post(
            "/post_offer/sell",
            data={"resource": resource, "amount": str(amount), "price": str(price)},
            description=f"Sell {amount}x {resource} at ${price}",
        )

    def buy_market_offer(self, offer_id, amount):
        """Buy from an existing market offer."""
        return self._post(
            f"/buy_offer/{offer_id}",
            data={f"amount_{offer_id}": str(amount)},
            description=f"Buy {amount} from offer {offer_id}",
        )


# ---------------------------------------------------------------------------
# Decision Engine
# ---------------------------------------------------------------------------
class AIDecisionEngine:
    """
    Priority-based decision engine.

    Decision order (highest to lowest priority):
      1. CRITICAL: Fix energy deficit (can't produce anything without power)
      2. CRITICAL: Fix food deficit (population starves)
      3. HIGH: Build distribution centers (need CG distribution)
      4. HIGH: Build resource extraction (raw materials)
      5. MEDIUM: Build processing (steel, aluminium, components)
      6. MEDIUM: Build consumer goods (retail)
      7. MEDIUM: Build happiness/productivity (public works)
      8. LOW: Military buildup
      9. LOW: Expand (new province, land, cities)
    """

    def __init__(self, state: GameState, client: GameClient):
        self.state = state
        self.client = client
        self.decisions = []
        self.gold_spent = 0

    def run(self):
        """Execute the full decision cycle."""
        logger.info("=" * 60)
        logger.info("AI Decision Cycle Starting")
        logger.info("=" * 60)

        # Phase 1: Critical fixes
        self._fix_energy_deficit()
        self._fix_food_deficit()
        self._fix_distribution()

        # Phase 2: Economic growth
        self._grow_resource_extraction()
        self._grow_processing()
        self._grow_consumer_goods()

        # Phase 3: Quality of life
        self._grow_happiness()

        # Phase 4: Military
        self._grow_military()

        # Phase 5: Expansion
        self._consider_expansion()

        logger.info("=" * 60)
        logger.info(
            "Cycle complete: %d actions, $%s spent",
            len(self.decisions),
            f"{self.gold_spent:,.0f}",
        )
        logger.info("=" * 60)

        return self.decisions

    def _can_afford(self, gold_cost, resource_costs=None):
        """Check if we can afford a building."""
        if self.state.available_gold - self.gold_spent < gold_cost:
            return False
        if resource_costs:
            for res, qty in resource_costs.items():
                if self.state.resources.get(res, 0) < qty:
                    return False
        return True

    def _deduct_costs(self, gold_cost, resource_costs=None):
        """Track spending (actual deduction happens server-side)."""
        self.gold_spent += gold_cost
        if resource_costs:
            for res, qty in resource_costs.items():
                self.state.resources[res] = self.state.resources.get(res, 0) - qty

    def _find_best_province(self, building_name):
        """Find the province with the most free slots for this building type."""
        is_city = building_name in CITY_SLOT_BUILDINGS
        best = None
        best_free = 0
        for p in self.state.provinces:
            free = (
                self.state.get_free_city_slots(p)
                if is_city
                else self.state.get_free_land_slots(p)
            )
            if free > best_free:
                best = p
                best_free = free
        return best, best_free

    def _build_if_possible(self, building_name, reason, max_count=None):
        """Try to build a building. Returns number built."""
        if max_count is None:
            max_count = MAX_BUILD_PER_TICK

        building_id = self.state.building_id_map.get(building_name)
        if not building_id:
            logger.debug("No building_id for %s, skipping", building_name)
            return 0

        gold_cost = BUILDING_COSTS.get(building_name, 0)
        res_cost = BUILDING_RESOURCE_COSTS.get(building_name, {})

        built = 0
        for _ in range(max_count):
            if not self._can_afford(gold_cost, res_cost):
                break

            province, free = self._find_best_province(building_name)
            if not province or free < 1:
                break

            self.client.build(building_name, building_id, province["id"], 1)
            self._deduct_costs(gold_cost, res_cost)

            # Update local state
            pid = province["id"]
            if pid not in self.state.buildings:
                self.state.buildings[pid] = {}
            self.state.buildings[pid][building_name] = (
                self.state.buildings[pid].get(building_name, 0) + 1
            )
            self.state.total_buildings[building_name] = (
                self.state.total_buildings.get(building_name, 0) + 1
            )

            built += 1
            self.decisions.append(f"{reason}: built {building_name} in province {pid}")

        return built

    # ----- Phase 1: Critical Fixes -----

    def _fix_energy_deficit(self):
        """If energy production <= consumption, build power plants."""
        self.state._calc_energy()
        deficit = self.state.energy_consumption - self.state.energy_production

        if deficit <= 0 and self.state.energy_surplus >= 2:
            # Even if surplus is fine, ensure we have at least 1 power plant
            # so we can start building energy-consuming buildings
            if self.state.energy_production > 0:
                return
            # No power at all — build at least one plant for bootstrapping
            deficit = 0

        # Need at least 3 surplus for growth headroom
        needed = max(deficit + 3, 3)

        # Priority order for power: coal (cheap) → oil → solar → hydro → nuclear
        power_options = [
            ("coal_burners", 4),  # 4 energy each
            ("oil_burners", 5),  # 5 energy each
            ("solar_fields", 3),  # 3 energy, no fuel
            ("hydro_dams", 6),  # 6 energy, no fuel
            ("nuclear_reactors", 15),  # 15 energy, expensive
        ]

        for building, energy_per in power_options:
            if needed <= 0:
                break
            count_needed = math.ceil(needed / energy_per)
            count_needed = min(count_needed, MAX_BUILD_PER_TICK)

            built = self._build_if_possible(
                building,
                f"CRITICAL/energy deficit={deficit}",
                max_count=count_needed,
            )
            needed -= built * energy_per

    def _fix_food_deficit(self):
        """Ensure rations production covers population needs."""
        rations = self.state.resources.get("rations", 0)
        rations_rate = self.state.resource_production_rate("rations")

        # If rations are declining and stock is low, build farms
        if rations_rate >= 0 and rations > 100000:
            return

        needed_farms = max(1, math.ceil(abs(min(0, rations_rate)) / 12) + 1)
        needed_farms = min(needed_farms, MAX_BUILD_PER_TICK)

        self._build_if_possible(
            "farms",
            f"CRITICAL/food deficit (rate={rations_rate}, stock={rations})",
            max_count=needed_farms,
        )

    def _fix_distribution(self):
        """Ensure enough distribution centers for population."""
        # Each distribution center handles 50k population, produces 8 CG
        dist_count = self.state.total_buildings.get("distribution_centers", 0)
        capacity = dist_count * 50000
        pop = self.state.population

        if capacity >= pop * 1.2:  # 20% headroom
            return

        needed = math.ceil((pop * 1.2 - capacity) / 50000)
        needed = min(needed, MAX_BUILD_PER_TICK)

        self._build_if_possible(
            "distribution_centers",
            f"HIGH/distribution gap (cap={capacity}, pop={pop})",
            max_count=needed,
        )

    # ----- Phase 2: Economic Growth -----

    def _grow_resource_extraction(self):
        """Build resource extraction buildings where supply is low."""
        # Priority: resources with negative or near-zero production rates
        extraction = [
            ("lumber_mills", "lumber"),
            ("iron_mines", "iron"),
            ("coal_mines", "coal"),
            ("copper_mines", "copper"),
            ("bauxite_mines", "bauxite"),
            ("lead_mines", "lead"),
            ("pumpjacks", "oil"),
            ("farms", "rations"),
            ("uranium_mines", "uranium"),
        ]

        for building, resource in extraction:
            rate = self.state.resource_production_rate(resource)
            stock = self.state.resources.get(resource, 0)

            # Build if negative rate or very low stock
            if rate < 0 or (rate < 5 and stock < 50000):
                self._build_if_possible(
                    building,
                    f"ECON/extract {resource} (rate={rate}, stock={stock})",
                    max_count=2,
                )

    def _grow_processing(self):
        """Build processing buildings if we have enough raw materials."""
        processors = [
            ("steel_mills", "steel", {"coal": 35, "iron": 35}),
            ("aluminium_refineries", "aluminium", {"bauxite": 15}),
            ("oil_refineries", "gasoline", {"oil": 20}),
            (
                "component_factories",
                "components",
                {"copper": 20, "steel": 10, "aluminium": 15},
            ),
            ("ammunition_factories", "ammunition", {"copper": 10, "lead": 20}),
        ]

        for building, output, inputs in processors:
            # Only build if we have surplus of all input resources
            can_support = True
            for res, per_tick in inputs.items():
                rate = self.state.resource_production_rate(res)
                stock = self.state.resources.get(res, 0)
                # Need positive rate AND enough stock for multiple ticks
                if rate < per_tick and stock < per_tick * 20:
                    can_support = False
                    break

            if can_support:
                output_rate = self.state.resource_production_rate(output)
                if output_rate < 20:  # Can use more
                    self._build_if_possible(
                        building,
                        f"ECON/process {output} (rate={output_rate})",
                        max_count=1,
                    )

    def _grow_consumer_goods(self):
        """Build consumer goods buildings for tax income."""
        cg_rate = self.state.resource_production_rate("consumer_goods")

        # Need CG proportional to population (~1 per 5k pop)
        target_cg = self.state.population / 5000
        if cg_rate >= target_cg:
            return

        # Priority: distribution centers (cheapest CG/gold), then gas stations, etc.
        cg_buildings = [
            ("distribution_centers", 8),
            ("gas_stations", 12),
            ("general_stores", 10),
            ("farmers_markets", 16),
        ]

        for building, cg_per in cg_buildings:
            if cg_rate >= target_cg:
                break
            built = self._build_if_possible(
                building,
                f"ECON/consumer_goods (rate={cg_rate:.0f}, target={target_cg:.0f})",
                max_count=2,
            )
            cg_rate += built * cg_per

    # ----- Phase 3: Happiness & Productivity -----

    def _grow_happiness(self):
        """Build public works if happiness is low."""
        if self.state.happiness >= 85:
            return  # Happy enough

        # Priority: city parks (happiness + pollution reduction), then others
        happiness_buildings = [
            ("city_parks", 5),
            ("primary_school", 2),
            ("high_school", 3),
            ("libraries", 5),
            ("hospitals", 8),
        ]

        for building, _happiness_per in happiness_buildings:
            if self.state.happiness >= 80:
                break
            self._build_if_possible(
                building,
                f"QOL/happiness={self.state.happiness:.0f}",
                max_count=2,
            )

    # ----- Phase 4: Military -----

    def _grow_military(self):
        """Build military proportional to economy size."""
        if self.state.available_gold - self.gold_spent < 2000000:
            return  # Not enough spare gold

        total_soldiers = self.state.military.get("soldiers", 0)
        total_tanks = self.state.military.get("tanks", 0)
        total_artillery = self.state.military.get("artillery", 0)

        # Target: 1 soldier per 1000 population, some tanks and artillery
        target_soldiers = int(self.state.population / 1000)
        target_tanks = int(target_soldiers / 20)
        target_artillery = int(target_soldiers / 30)

        # Buy soldiers
        soldier_deficit = target_soldiers - total_soldiers
        if soldier_deficit > 0:
            buy_count = min(soldier_deficit, MAX_MILITARY_PER_TICK)
            cost = buy_count * MILDICT["soldiers"]["price"]
            rations_needed = buy_count * 500
            if (
                self._can_afford(cost)
                and self.state.resources.get("rations", 0) > rations_needed
                and self.state.manpower >= buy_count
            ):
                self.client.buy_military("soldiers", buy_count)
                self._deduct_costs(cost)
                self.decisions.append(
                    f"MIL/soldiers: bought {buy_count} "
                    f"(was {total_soldiers}, target {target_soldiers})"
                )

        # Buy tanks if we can afford and have resources
        tank_deficit = target_tanks - total_tanks
        if tank_deficit > 0:
            buy_count = min(tank_deficit, 10)
            cost = buy_count * MILDICT["tanks"]["price"]
            res = MILDICT["tanks"]["resources"]
            res_scaled = {r: v * buy_count for r, v in res.items()}
            if (
                self._can_afford(cost)
                and all(
                    self.state.resources.get(r, 0) >= v for r, v in res_scaled.items()
                )
                and self.state.manpower >= buy_count * 4
            ):
                self.client.buy_military("tanks", buy_count)
                self._deduct_costs(cost)
                self.decisions.append(
                    f"MIL/tanks: bought {buy_count} "
                    f"(was {total_tanks}, target {target_tanks})"
                )

        # Buy artillery
        arty_deficit = target_artillery - total_artillery
        if arty_deficit > 0:
            buy_count = min(arty_deficit, 10)
            cost = buy_count * MILDICT["artillery"]["price"]
            res = MILDICT["artillery"]["resources"]
            res_scaled = {r: v * buy_count for r, v in res.items()}
            if (
                self._can_afford(cost)
                and all(
                    self.state.resources.get(r, 0) >= v for r, v in res_scaled.items()
                )
                and self.state.manpower >= buy_count * 2
            ):
                self.client.buy_military("artillery", buy_count)
                self._deduct_costs(cost)
                self.decisions.append(
                    f"MIL/artillery: bought {buy_count} "
                    f"(was {total_artillery}, target {target_artillery})"
                )

    # ----- Phase 5: Expansion -----

    def _consider_expansion(self):
        """Buy land/cities or new provinces when economically viable."""
        # Buy land if any province has < 3 free land slots
        for province in self.state.provinces:
            free_land = self.state.get_free_land_slots(province)
            if free_land < 3 and self._can_afford(1000000):
                self.client.buy_land(province["id"], 1)
                self._deduct_costs(500000)
                province["land"] = (province.get("land") or 0) + 1
                self.decisions.append(
                    f"EXPAND/land: +1 land province "
                    f"{province['id']} (was {free_land} free)"
                )

        # Buy city slots if any province has < 3 free city slots
        for province in self.state.provinces:
            free_city = self.state.get_free_city_slots(province)
            if free_city < 3 and self._can_afford(1000000):
                self.client.buy_city(province["id"], 1)
                self._deduct_costs(500000)
                province["cityCount"] = (province.get("cityCount") or 0) + 1
                self.decisions.append(
                    f"EXPAND/city: +1 city province "
                    f"{province['id']} (was {free_city} free)"
                )

        # Consider buying a new province if very wealthy
        province_cost = int(8000000 * (1 + 0.16 * self.state.province_count))
        if (
            self.state.available_gold - self.gold_spent > province_cost * 3
            and self.state.province_count < 20
        ):
            name = f"Colony-{self.state.province_count + 1}"
            self.client.create_province(name)
            self._deduct_costs(province_cost)
            self.decisions.append(
                f"EXPAND/province: created '{name}' (cost={province_cost:,.0f})"
            )


# ---------------------------------------------------------------------------
# Decision Logger (for self-improvement tracking)
# ---------------------------------------------------------------------------
class DecisionLogger:
    """Logs AI decisions to a JSON file for analysis and self-improvement."""

    LOG_DIR = os.path.join(os.path.dirname(__file__), "ai_logs")

    @classmethod
    def log_cycle(cls, state: GameState, decisions: list, actions: list):
        """Log a full decision cycle."""
        os.makedirs(cls.LOG_DIR, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_entry = {
            "timestamp": timestamp,
            "user_id": state.user_id,
            "state_snapshot": {
                "gold": state.gold,
                "population": state.population,
                "happiness": state.happiness,
                "pollution": state.pollution,
                "energy_production": state.energy_production,
                "energy_consumption": state.energy_consumption,
                "province_count": state.province_count,
                "manpower": state.manpower,
                "resources": state.resources,
                "total_buildings": state.total_buildings,
                "military": state.military,
            },
            "decisions": decisions,
            "actions": actions,
        }

        filepath = os.path.join(cls.LOG_DIR, f"cycle_{timestamp}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(log_entry, f, indent=2, default=str)
            logger.info("Decision log saved: %s", filepath)
        except Exception as e:
            logger.warning("Failed to save decision log: %s", e)

        # Also maintain a rolling summary
        cls._update_summary(log_entry)

    @classmethod
    def _update_summary(cls, entry):
        """Append key metrics to a rolling CSV for trend analysis."""
        summary_path = os.path.join(cls.LOG_DIR, "summary.csv")
        is_new = not os.path.exists(summary_path)

        try:
            with open(summary_path, "a") as f:
                if is_new:
                    f.write(
                        "timestamp,gold,population,happiness,pollution,"
                        "energy_prod,energy_cons,provinces,decisions_count\n"
                    )
                snap = entry["state_snapshot"]
                f.write(
                    f"{entry['timestamp']},"
                    f"{snap['gold']},"
                    f"{snap['population']},"
                    f"{snap['happiness']:.1f},"
                    f"{snap['pollution']:.1f},"
                    f"{snap['energy_production']},"
                    f"{snap['energy_consumption']},"
                    f"{snap['province_count']},"
                    f"{len(entry['decisions'])}\n"
                )
        except Exception as e:
            logger.warning("Failed to update summary: %s", e)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_ai_agent(user_id=None):
    """
    Main AI agent function. Reads state, makes decisions, executes actions.

    Can be called directly or from a Celery task.
    """
    uid = user_id or AI_USER_ID
    start = time.time()

    try:
        # 1. Read game state
        state = GameState(uid)
        state.load()

        # 2. Create HTTP client
        client = GameClient()
        client.login()

        # 3. Run decision engine
        engine = AIDecisionEngine(state, client)
        decisions = engine.run()

        # 4. Log for self-improvement
        DecisionLogger.log_cycle(state, decisions, client.actions_taken)

        elapsed = time.time() - start
        logger.info(
            "AI agent completed in %.1fs, %d decisions made", elapsed, len(decisions)
        )
        return {
            "status": "ok",
            "decisions": len(decisions),
            "elapsed": round(elapsed, 1),
            "gold_spent": engine.gold_spent,
        }

    except Exception as e:
        logger.exception("AI agent failed: %s", e)
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# CLI entry point for manual runs
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Allow passing user_id as argument
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else AI_USER_ID
    result = run_ai_agent(uid)
    print(json.dumps(result, indent=2))
