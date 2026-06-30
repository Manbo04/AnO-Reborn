from attack_scripts.Nations import Military, Nation
from units import Units
from database import get_db_connection

# Setup test attacker and defender
cId = 1 # Manbo04 usually? Or someone
eId = 2 # Some enemy

# Mock attacker units
attacker_units = {"soldiers": 100, "tanks": 10}
attacker = Units(cId, attacker_units)

# Mock defender units
defender_military = Military.get_military(eId)
defenselst = ["soldiers", "tanks", "artillery"]
defenseunits = {u: defender_military.get(u, 0) for u in defenselst}
defender = Units(eId, defenseunits, selected_units_list=defenselst)

# Run the fight
try:
    winner, win_condition, attack_effects = Military.fight(attacker, defender)
    print("WINNER:", winner)
    print("CONDITION:", win_condition)
    print("EFFECTS:", attack_effects)
except Exception as e:
    import traceback
    traceback.print_exc()
