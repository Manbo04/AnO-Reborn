import re
import os

def clean_file(path):
    with open(path, 'r') as f:
        content = f.read()

    # 1. Replace =(%s) with =%s
    content = re.sub(r'=\(%s\)', r'=%s', content)

    # 2. Fix messy implicit concatenation: ("string " "string")
    # This regex is a bit simplistic, but we can target specific patterns.
    # Actually, running 'black' or similar formatter might fix indentation and concatenation if we just configure it.
    
    with open(path, 'w') as f:
        f.write(content)

for p in ['market.py', 'admin_tools.py', 'world_map_bp.py', 'ads_bp.py']:
    clean_file(p)
