import math

class variables:
    RATIONS_PER = 100
    NO_FOOD_TAX_MULTIPLIER = 0.7

total_population = 1000000
current_rations_list = [10000, 5000, 0]
dist_cap = 10000

for current_rations in current_rations_list:
    needed_rations = max(int(total_population // variables.RATIONS_PER), 1)
    effective_rations = min(current_rations, dist_cap)
    rcp = min(0.0, (effective_rations / needed_rations) - 1.0)
    
    food_tax_multiplier = 1.0 + (rcp * (1.0 - variables.NO_FOOD_TAX_MULTIPLIER))
    print(f"Rations: {current_rations}, RCP: {rcp}, Multiplier: {food_tax_multiplier}")

