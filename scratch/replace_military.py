import re

with open('templates/coalition.html', 'r') as f:
    content = f.read()

def replace_mil(match):
    table_content = match.group(1)
    return """<h2 class="templatecontentheaderleft" style="margin-top: 0;"><span class="material-icons-outlined">military_tech</span> Military</h2>
<div class="stat-grid">
    <div class="templatedivflex2left stat-card">
        <strong class="stat-label">Military power</strong>
        <span class="stat-value">power#</span>
    </div>
    <div class="templatedivflex2left stat-card">
        <strong class="stat-label">Land Military</strong>
        <span class="stat-value">30%</span>
    </div>
    <div class="templatedivflex2left stat-card">
        <strong class="stat-label">Air Military</strong>
        <span class="stat-value">60%</span>
    </div>
    <div class="templatedivflex2left stat-card">
        <strong class="stat-label">Water Military</strong>
        <span class="stat-value">10%</span>
    </div>
    <div class="templatedivflex2left stat-card" style="grid-column: 1 / -1; display: flex; justify-content: center;">
        <a class="forgotpasscode loginsignupforgot" href="#">View stats</a>
    </div>
</div>"""

pattern = r'<table class="templatetable">\s*<tr>\s*<th><span class="material-icons-outlined">\s*military_tech\s*</span>Military</th>(.*?)</table>'

# Wait, in coalition.html it might not have <tr> around <th>! Let's check above output:
#                     <table class="templatetable">
#                         <th><span class="material-icons-outlined">
#                             military_tech
#                             </span>Military</th>
#                         </tr>
# YES! it misses opening <tr>!
