import re

with open('variables.py', 'r') as f:
    content = f.read()

replacements = {
    # Update Steel Mills inputs based on worldsteel (1.4t iron, 0.8t coal per 1t steel)
    # Output is 48 steel, so 67 iron and 38 coal.
    '"steel_mills_convert_minus": [{"coal": 140}, {"iron": 140}]': '"steel_mills_convert_minus": [{"coal": 38}, {"iron": 67}]',
    '"minus": {"coal": 140, "iron": 140}': '"minus": {"coal": 38, "iron": 67}',
    
    # Update Aluminium Refineries (4t bauxite per 1t aluminium)
    # Output is 64 aluminium, so 256 bauxite.
    '"aluminium_refineries_convert_minus": [{"bauxite": 60}]': '"aluminium_refineries_convert_minus": [{"bauxite": 256}]',
    '"minus": {"bauxite": 60}': '"minus": {"bauxite": 256}',
    
    # Update Oil Refineries (~2t oil per 1t gasoline)
    # Output is 44 gasoline, so 88 oil.
    '"oil_refineries_convert_minus": [{"oil": 80}]': '"oil_refineries_convert_minus": [{"oil": 88}]',
    '"minus": {"oil": 80}': '"minus": {"oil": 88}',

    # Update raw outputs to support the new factory consumptions (~1 mine per factory)
    '"coal_mines_plus": {"coal": 124}': '"coal_mines_plus": {"coal": 120}',
    '"plus": {"coal": 124}': '"plus": {"coal": 120}',
    
    '"bauxite_mines_plus": {"bauxite": 80}': '"bauxite_mines_plus": {"bauxite": 260}',
    '"plus": {"bauxite": 80}': '"plus": {"bauxite": 260}',
    
    '"copper_mines_plus": {"copper": 100}': '"copper_mines_plus": {"copper": 120}',
    '"plus": {"copper": 100}': '"plus": {"copper": 120}',
    
    '"lead_mines_plus": {"lead": 76}': '"lead_mines_plus": {"lead": 80}',
    '"plus": {"lead": 76}': '"plus": {"lead": 80}',
    
    '"iron_mines_plus": {"iron": 92}': '"iron_mines_plus": {"iron": 70}',
    '"plus": {"iron": 92}': '"plus": {"iron": 70}',
    
    '"pumpjacks_plus": {"oil": 96}': '"pumpjacks_plus": {"oil": 100}',
    '"plus": {"oil": 96}': '"plus": {"oil": 100}',
    
    '"farms_plus": {"rations": 48}': '"farms_plus": {"rations": 100}',
    '"plus": {"rations": 48}': '"plus": {"rations": 100}',
    
    '"uranium_mines_plus": {"uranium": 48}': '"uranium_mines_plus": {"uranium": 40}',
    '"plus": {"uranium": 48}': '"plus": {"uranium": 40}',
    
    '"lumber_mills_plus": {"lumber": 140}': '"lumber_mills_plus": {"lumber": 150}',
    '"plus": {"lumber": 140}': '"plus": {"lumber": 150}',
}

for k, v in replacements.items():
    if k not in content:
        print(f"Warning: could not find {k}")
    content = content.replace(k, v)

with open('variables.py', 'w') as f:
    f.write(content)
print("Updated economy based on worldsteel!")
