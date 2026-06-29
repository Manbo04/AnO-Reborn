import re
import sys
import glob

def refactor_table(match):
    table_content = match.group(1)
    
    # We will build the new HTML
    new_html = []
    
    # Extract title if present
    # Usually in the form <tr><th><span...>...</span>Title</th></tr>
    th_match = re.search(r'<tr>\s*<th[^>]*>(.*?)</th>\s*</tr>', table_content, re.DOTALL)
    
    if th_match:
        # Title might contain span for icon
        title_inner = th_match.group(1).strip()
        # Ensure it looks good, maybe replace some whitespace
        new_html.append(f'<h2 class="templatecontentheaderleft" style="margin-top: 0;">{title_inner}</h2>')
        
    new_html.append('<div class="stat-grid">')
    
    # Extract all rows with 2 tds
    td_rows = re.findall(r'<tr>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>', table_content, re.DOTALL)
    
    if not td_rows:
        # If we couldn't parse simple 2-td rows, we might need a more complex parser. 
        # For now, return original if we can't parse it well.
        # Check if there are ANY tds
        if '<td' in table_content:
            return match.group(0) # Abort
            
    for td1, td2 in td_rows:
        td1 = td1.strip().replace(':', '') # Remove trailing colon if exists
        td2 = td2.strip()
        
        # In case the table row actually contained <tr><td>something</td><td>something</td></tr>
        new_html.append('    <div class="templatedivflex2left stat-card">')
        new_html.append(f'        <strong class="stat-label">{td1}</strong>')
        new_html.append(f'        <span class="stat-value">{td2}</span>')
        new_html.append('    </div>')
        
    new_html.append('</div>')
    
    # If the table didn't have <th> but we found td_rows, we still convert
    if not th_match and not td_rows:
        return match.group(0)
        
    return "\n".join(new_html)


def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
        
    # Find all <table class="templatetable">...</table>
    # We handle optional other classes too
    pattern = re.compile(r'<table[^>]*class="[^"]*templatetable[^"]*"[^>]*>(.*?)</table>', re.DOTALL)
    
    new_content = pattern.sub(refactor_table, content)
    
    if new_content != content:
        print(f"Modified {filepath}")
        with open(filepath, 'w') as f:
            f.write(new_content)

files = glob.glob('/Volumes/Be Careful 1/MacOffload/AnO-Reborn/templates/*.html')
for f in files:
    process_file(f)
