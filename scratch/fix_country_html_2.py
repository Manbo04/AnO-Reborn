import re

with open('templates/country.html', 'r') as f:
    lines = f.readlines()

out = []
skip_next_endif = False
for i, line in enumerate(lines):
    if '{% if revenue["gross"]' in line or '{% if revenue["net"]' in line:
        skip_next_endif = True
        continue
    if skip_next_endif and '{% endif %}' in line:
        # Check if this endif is for the revenue line we just skipped.
        # Since the structure is just {% if ... %} \n <tr>...</tr> \n {% endif %}
        skip_next_endif = False
        continue
    out.append(line)

with open('templates/country.html', 'w') as f:
    f.writelines(out)

print("Done fixing country.html v2")
