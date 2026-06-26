import re

with open('variables.py', 'r') as f:
    content = f.read()

replacements = {
    # Prices
    '"farms_price": 500000': '"farms_price": 1500000',
    '"lumber_mills_price": 1000000': '"lumber_mills_price": 2200000',
    '"coal_mines_price": 1500000': '"coal_mines_price": 3500000',
    '"iron_mines_price": 1800000': '"iron_mines_price": 3800000',
    '"bauxite_mines_price": 1200000': '"bauxite_mines_price": 2400000',
    '"copper_mines_price": 1400000': '"copper_mines_price": 2800000',
    '"lead_mines_price": 1300000': '"lead_mines_price": 2600000',
    '"pumpjacks_price": 1500000': '"pumpjacks_price": 3000000',

    # INFRA values
    '"farms_plus": {"rations": 12}': '"farms_plus": {"rations": 48}',
    '"pumpjacks_plus": {"oil": 24}': '"pumpjacks_plus": {"oil": 96}',
    '"coal_mines_plus": {"coal": 31}': '"coal_mines_plus": {"coal": 124}',
    '"bauxite_mines_plus": {"bauxite": 20}': '"bauxite_mines_plus": {"bauxite": 80}',
    '"copper_mines_plus": {"copper": 25}': '"copper_mines_plus": {"copper": 100}',
    '"uranium_mines_plus": {"uranium": 12}': '"uranium_mines_plus": {"uranium": 48}',
    '"lead_mines_plus": {"lead": 19}': '"lead_mines_plus": {"lead": 76}',
    '"iron_mines_plus": {"iron": 23}': '"iron_mines_plus": {"iron": 92}',
    '"lumber_mills_plus": {"lumber": 35}': '"lumber_mills_plus": {"lumber": 140}',

    '"component_factories_convert_minus": [\n        {"copper": 20},\n        {"steel": 10},\n        {"aluminium": 15},\n    ]': '"component_factories_convert_minus": [\n        {"copper": 80},\n        {"steel": 40},\n        {"aluminium": 60},\n    ]',
    '"component_factories_plus": {"components": 5}': '"component_factories_plus": {"components": 20}',

    '"steel_mills_convert_minus": [{"coal": 35}, {"iron": 35}]': '"steel_mills_convert_minus": [{"coal": 140}, {"iron": 140}]',
    '"steel_mills_plus": {"steel": 12}': '"steel_mills_plus": {"steel": 48}',

    '"ammunition_factories_convert_minus": [{"copper": 10}, {"lead": 20}]': '"ammunition_factories_convert_minus": [{"copper": 40}, {"lead": 80}]',
    '"ammunition_factories_plus": {"ammunition": 12}': '"ammunition_factories_plus": {"ammunition": 48}',

    '"aluminium_refineries_convert_minus": [{"bauxite": 15}]': '"aluminium_refineries_convert_minus": [{"bauxite": 60}]',
    '"aluminium_refineries_plus": {"aluminium": 16}': '"aluminium_refineries_plus": {"aluminium": 64}',

    '"oil_refineries_convert_minus": [{"oil": 20}]': '"oil_refineries_convert_minus": [{"oil": 80}]',
    '"oil_refineries_plus": {"gasoline": 11}': '"oil_refineries_plus": {"gasoline": 44}',

    # NEW_INFRA values
    '"plus": {"rations": 12}': '"plus": {"rations": 48}',
    '"plus": {"oil": 24}': '"plus": {"oil": 96}',
    '"plus": {"coal": 31}': '"plus": {"coal": 124}',
    '"plus": {"bauxite": 20}': '"plus": {"bauxite": 80}',
    '"plus": {"copper": 25}': '"plus": {"copper": 100}',
    '"plus": {"uranium": 12}': '"plus": {"uranium": 48}',
    '"plus": {"lead": 19}': '"plus": {"lead": 76}',
    '"plus": {"iron": 23}': '"plus": {"iron": 92}',
    '"plus": {"lumber": 35}': '"plus": {"lumber": 140}',

    '"minus": {"copper": 20, "steel": 10, "aluminium": 15}': '"minus": {"copper": 80, "steel": 40, "aluminium": 60}',
    '"plus": {"components": 5}': '"plus": {"components": 20}',

    '"minus": {"coal": 35, "iron": 35}': '"minus": {"coal": 140, "iron": 140}',
    '"plus": {"steel": 12}': '"plus": {"steel": 48}',

    '"minus": {"copper": 10, "lead": 20}': '"minus": {"copper": 40, "lead": 80}',
    '"plus": {"ammunition": 12}': '"plus": {"ammunition": 48}',

    '"minus": {"bauxite": 15}': '"minus": {"bauxite": 60}',
    '"plus": {"aluminium": 16}': '"plus": {"aluminium": 64}',

    '"minus": {"oil": 20}': '"minus": {"oil": 80}',
    '"plus": {"gasoline": 11}': '"plus": {"gasoline": 44}',
}

for k, v in replacements.items():
    if k not in content:
        print(f"Warning: could not find {k}")
    content = content.replace(k, v)

with open('variables.py', 'w') as f:
    f.write(content)
print("Updated variables.py")
