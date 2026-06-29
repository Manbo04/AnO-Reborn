import glob
import re

def replace_table(match):
    table_content = match.group(1)
    
    # We ignore tables with jinja tags that span rows, but our regex won't match <tr> inside {% if %} if we count exactly.
    # Wait, in provinces.html we had {% if %} around <td>. Our regex requires exactly 2 <td>.
    
    th_match = re.search(r'<tr>\s*<th[^>]*>(.*?)</th>\s*</tr>', table_content, re.DOTALL)
    if not th_match:
        return match.group(0)
    
    title_inner = th_match.group(1).strip()
    
    new_html = [f'<h2 class="templatecontentheaderleft" style="margin-top: 0;">{title_inner}</h2>', '<div class="stat-grid">']
    
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
    
    tr_count = len(re.findall(r'<tr[^>]*>', table_content))
    if tr_count != len(td_rows) + 1:
        return match.group(0)
        
    return "\n".join(new_html)

pattern = r'<table\s+class="[^"]*templatetable[^"]*"[^>]*>(.*?)</table>'

files = glob.glob('templates/*.html')
for filepath in files:
    if filepath == 'templates/provinces.html':
        continue # handled manually
    with open(filepath, 'r') as f:
        content = f.read()
    new_content = re.sub(pattern, replace_table, content, flags=re.DOTALL)
    if new_content != content:
        print(f"Modified {filepath}")
        with open(filepath, 'w') as f:
            f.write(new_content)
