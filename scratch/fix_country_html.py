import re

with open('templates/country.html', 'r') as f:
    content = f.read()

# Replace {% if revenue["gross"]... %} and {% if revenue["net"]... %} followed by a <tr>...</tr> and an {% endif %}
# We'll do this by matching the pattern:
# {% if revenue["gross"]["..."] > 0 %}
# <tr>...</tr>
# {% endif %}

pattern_gross = re.compile(r'\{%\s*if revenue\["gross"\]\["[^"]*"\]\s*>\s*0\s*%\}\s*(<tr>.*?</tr>)\s*\{%\s*endif\s*%\}', re.DOTALL)
content = pattern_gross.sub(r'\1', content)

pattern_net = re.compile(r'\{%\s*if revenue\["net"\]\["[^"]*"\]\s*!=\s*0\s*%\}\s*(<tr>.*?</tr>)\s*\{%\s*endif\s*%\}', re.DOTALL)
content = pattern_net.sub(r'\1', content)

pattern_net2 = re.compile(r'\{%\s*if revenue\["net"\]\["[^"]*"\]\s*>\s*0\s*%\}\s*(<tr>.*?</tr>)\s*\{%\s*endif\s*%\}', re.DOTALL)
content = pattern_net2.sub(r'\1', content)

with open('templates/country.html', 'w') as f:
    f.write(content)

print("Done fixing country.html")
