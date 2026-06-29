import re

with open('/Volumes/Be Careful 1/MacOffload/AnO-Reborn/templates/provinces.html', 'r') as f:
    content = f.read()

pattern = r'<table class="templatetable inverttable ">(.*?)</table>'

def replace_table(match):
    return """<h2 class="templatecontentheaderleft" style="margin-top: 0;"><span class="material-icons-outlined">account_balance</span>{{ name }}</h2>
                    <div class="stat-grid">
                        <div class="templatedivflex2left stat-card">
                            <strong class="stat-label"><span class="material-icons-outlined">people_alt</span> Population</strong>
                            <span class="stat-value">{{ population }}</span>
                        </div>
                        <div class="templatedivflex2left stat-card">
                            <strong class="stat-label"><span class="material-icons-outlined">sentiment_satisfied</span> Happiness</strong>
                            <span class="stat-value">{{ happiness }}%</span>
                        </div>
                        <div class="templatedivflex2left stat-card">
                            <strong class="stat-label"><span class="material-icons-outlined">arrow_circle_up</span> Productivity</strong>
                            <span class="stat-value">{{ productivity }}%</span>
                        </div>
                        <div class="templatedivflex2left stat-card">
                            <strong class="stat-label"><span class="material-icons-outlined">business</span> City slots</strong>
                            <span class="stat-value">{{ cityCount }}</span>
                        </div>
                        <div class="templatedivflex2left stat-card">
                            <strong class="stat-label"><span class="material-icons-outlined">landscape</span> Land slots</strong>
                            <span class="stat-value">{{ land }}</span>
                        </div>
                        <div class="templatedivflex2left stat-card">
                            <strong class="stat-label"><span class="material-icons-outlined">power</span> Powered</strong>
                            <span class="stat-value">{% if energy > 0 %}Yes{% else %}No{% endif %}</span>
                        </div>
                    </div>"""

new_content = re.sub(pattern, replace_table, content, flags=re.DOTALL)

with open('/Volumes/Be Careful 1/MacOffload/AnO-Reborn/templates/provinces.html', 'w') as f:
    f.write(new_content)
