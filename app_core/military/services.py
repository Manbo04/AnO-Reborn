from .repositories import (
    ALL_UNITS,
    get_building_counts,
    get_user_units_with_stats,
    get_unit_costs,
    get_current_unit_quantity,
    get_manpower_and_gold,
    get_resource_balances,
    adjust_resources_batch,
    remove_units,
    add_units,
    update_manpower_and_gold,
    insert_revenue
)
from upgrades import get_upgrades

def compute_display_limits(cId, db, units_row=None):
    """Return limits as shown on the military page."""
    army_bases, harbours, aerodomes, admin_buildings, silos = get_building_counts(db, cId)

    raw = units_row or {}
    military = {}
    for unit in ALL_UNITS:
        val = raw.get(unit, 0)
        military[unit] = val["quantity"] if isinstance(val, dict) else int(val or 0)

    # Land units
    soldiers = max(0, army_bases * 5000 - military["soldiers"])
    tanks = max(0, army_bases * 200 - military["tanks"])
    artillery = max(0, army_bases * 200 - military["artillery"])

    # Air units share aerodome capacity
    air_units = military["fighters"] + military["bombers"] + military["apaches"]
    air_limit = max(0, aerodomes * 100 - air_units)
    bombers = air_limit
    fighters = air_limit
    apaches = air_limit

    # Naval units
    naval_units = military["submarines"] + military["destroyers"]
    naval_limit = max(0, harbours * 20 - naval_units)
    submarines = naval_limit
    destroyers = naval_limit
    cruisers = max(0, harbours * 10 - military["cruisers"])

    # Specials
    spies = max(0, admin_buildings * 1 - military["spies"])
    icbms = max(0, silos + 1 - military["icbms"])
    nukes = max(0, silos - military["nukes"])

    upgrades = get_upgrades(cId, db=db)
    if upgrades.get("increasedfunding"):
        spies = int(spies * 1.4)
        
    if not upgrades.get("icbmsilo"):
        icbms = 0
        
    if not upgrades.get("nucleartestingfacility"):
        nukes = 0

    return {
        "soldiers": soldiers,
        "tanks": tanks,
        "artillery": artillery,
        "bombers": bombers,
        "fighters": fighters,
        "apaches": apaches,
        "destroyers": destroyers,
        "cruisers": cruisers,
        "submarines": submarines,
        "spies": spies,
        "icbms": icbms,
        "nukes": nukes,
    }

def process_sell_units(db, cId, units, wantedUnits, mildict):
    unit_costs = get_unit_costs(db, units, mildict)
    if not unit_costs:
        return False, "Unit definition not found or inactive"
    
    unit_id = unit_costs["unit_id"]
    currentUnits = get_current_unit_quantity(db, cId, unit_id)
    if wantedUnits > currentUnits:
        return False, f"Not enough {units} (have {currentUnits})"
    
    price = unit_costs["gold_cost"]
    resources = unit_costs["resource_costs"]
    manpower_per_unit = unit_costs["manpower_cost"]
    totalPrice = wantedUnits * price
    
    sell_deltas = {res: wantedUnits * amt for res, amt in resources.items()}
    adjust_resources_batch(db, cId, sell_deltas)
    
    remove_units(db, cId, unit_id, wantedUnits)
    update_manpower_and_gold(db, cId, gold_delta=totalPrice, manpower_delta=(wantedUnits * manpower_per_unit))
    
    insert_revenue(db, cId, "revenue", f"Selling {wantedUnits} {units} for your military.", "", units, wantedUnits)
    return True, "Success"

def process_buy_units(db, cId, units, wantedUnits, mildict):
    unit_costs = get_unit_costs(db, units, mildict)
    if not unit_costs:
        return False, "Unit definition not found or inactive"
        
    units_dict, _ = get_user_units_with_stats(db, cId)
    limits = compute_display_limits(cId, db, units_dict)
    
    if wantedUnits > limits[units]:
        return False, f"Unit buy limit exceeded (allowed {limits[units]})"

    manpower_available, gold = get_manpower_and_gold(db, cId)
    price = unit_costs["gold_cost"]
    totalPrice = wantedUnits * price

    if totalPrice > gold:
        return False, f"Not enough money ({gold}/{totalPrice})"

    manpower_per_unit = unit_costs["manpower_cost"]
    needed_manpower = wantedUnits * manpower_per_unit
    if needed_manpower > manpower_available:
        return False, f"Not enough manpower ({manpower_available}/{needed_manpower})"

    resources = unit_costs["resource_costs"]
    balances = get_resource_balances(db, cId, resources.keys())
    for resource, amount in resources.items():
        currentResources = balances.get(resource, 0)
        requiredResources = amount * wantedUnits

        if requiredResources > currentResources:
            return False, f"{resource}: need {requiredResources-currentResources}"

    buy_deltas = {res: -(amt * wantedUnits) for res, amt in resources.items()}
    adjust_resources_batch(db, cId, buy_deltas)
    
    unit_id = unit_costs["unit_id"]
    add_units(db, cId, unit_id, wantedUnits)
    update_manpower_and_gold(db, cId, gold_delta=-totalPrice, manpower_delta=-needed_manpower)
    
    insert_revenue(db, cId, "expense", f"Buying {wantedUnits} {units} for your military.", "", units, wantedUnits)
    return True, "Success"
