import lxml.html
import glob
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        html = f.read()
    
    # We'll use a regex approach first to find tables, then parse each table with lxml to decide.
    # Parsing the whole document with lxml might mess up Jinja tags like {% if ... %} because lxml doesn't know Jinja.
    
    def replacer(match):
        table_html = match.group(0)
        
        # We can't parse with lxml directly if there are block-level jinja tags inside.
        # But for these stat tables, they usually just have {{ vars }} inside <td>.
        # Let's check if there's any {% ... %} inside the table that isn't simple.
        # Actually, let's just parse the table_html and see if it breaks.
        try:
            tree = lxml.html.fragment_fromstring(table_html)
        except Exception:
            return table_html
            
        if tree.tag != 'table':
            return table_html
            
        rows = tree.findall('.//tr')
        if not rows:
            return table_html
            
        first_row = rows[0]
        ths = first_row.findall('.//th')
        
        if len(ths) != 1:
            return table_html # Not a stat table
            
        title_html = lxml.html.tostring(ths[0], encoding='unicode', method='html')
        # strip <th> and </th>
        title_inner = re.sub(r'^<th[^>]*>', '', title_html)
        title_inner = re.sub(r'</th>$', '', title_inner).strip()
        
        stat_cards = []
        for row in rows[1:]:
            tds = row.findall('.//td')
            # Check for jinja tags that might be outside tds? Usually they are inside.
            # Wait, if there are {% if %} around <tr>, lxml might put them in weird places or drop them.
            if len(tds) != 2:
                # Might have colspan or something else, abort
                return table_html
            
            label_html = lxml.html.tostring(tds[0], encoding='unicode', method='html')
            label_inner = re.sub(r'^<td[^>]*>', '', label_html)
            label_inner = re.sub(r'</td>$', '', label_inner).strip()
            # Remove trailing colon
            label_inner = re.sub(r':$', '', label_inner.strip())
            
            val_html = lxml.html.tostring(tds[1], encoding='unicode', method='html')
            val_inner = re.sub(r'^<td[^>]*>', '', val_html)
            val_inner = re.sub(r'</td>$', '', val_inner).strip()
            
            stat_cards.append((label_inner, val_inner))
            
        # Build new html
        new_html = f'<h2 class="templatecontentheaderleft">{title_inner}</h2>\n<div class="stat-grid">\n'
        for label, val in stat_cards:
            new_html += f'    <div class="templatedivflex2left stat-card">\n'
            new_html += f'        <strong class="stat-label">{label}</strong>\n'
            new_html += f'        <span class="stat-value">{val}</span>\n'
            new_html += f'    </div>\n'
        new_html += '</div>'
        
        return new_html

    # Find tables that have class="templatetable..." 
    # Use re to find them, but be careful with nested tables (rare in these templates)
    pattern = re.compile(r'<table\s+class="[^"]*templatetable[^"]*"[^>]*>.*?</table>', re.DOTALL)
    
    new_html = pattern.sub(replacer, html)
    if new_html != html:
        print(f"Modified {filepath}")
        with open(filepath, 'w') as f:
            f.write(new_html)

files = glob.glob('/Volumes/Be Careful 1/MacOffload/AnO-Reborn/templates/*.html')
for f in files:
    process_file(f)
