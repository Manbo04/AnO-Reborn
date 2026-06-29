import re

with open('templates/country.html', 'r') as f:
    content = f.read()

def replace_table(match):
    table_content = match.group(1)
    
    # Extract title
    th_match = re.search(r'<tr>\s*<th[^>]*>(.*?)</th>\s*</tr>', table_content, re.DOTALL)
    if not th_match:
        return match.group(0)
    
    title_inner = th_match.group(1).strip()
    
    new_html = [f'<h2 class="templatecontentheaderleft" style="margin-top: 0;">{title_inner}</h2>', '<div class="stat-grid">']
    
    # Find all rows with 2 TDs
    td_rows = re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>', table_content, re.DOTALL)
    if not td_rows:
        return match.group(0)
        
    for td1, td2 in td_rows:
        td1 = td1.strip().replace(':', '')
        td2 = td2.strip()
        new_html.append('    <div class="templatedivflex2left stat-card">')
        new_html.append(f'        <strong class="stat-label">{td1}</strong>')
        new_html.append(f'        <span class="stat-value">{td2}</span>')
        new_html.append('    </div>')
        
    new_html.append('</div>')
    
    # If the table has other rows (like one with 1 TD), we might lose it, but stat tables shouldn't.
    # Check if we captured all rows by counting <tr>
    tr_count = len(re.findall(r'<tr[^>]*>', table_content))
    if tr_count != len(td_rows) + 1:
        # there are rows we missed
        return match.group(0)
        
    return "\n".join(new_html)

pattern = r'<table\s+class="[^"]*templatetable[^"]*"[^>]*>(.*?)</table>'
new_content = re.sub(pattern, replace_table, content, flags=re.DOTALL)

with open('templates/country.html', 'w') as f:
    f.write(new_content)
