import re

with open("wars/routes.py", "r") as f:
    content = f.read()

# Replace attacker_id -> attacker, defender_id -> defender, war_id -> id ONLY in SQL queries targeting `wars` table.
content = content.replace("SELECT peace_offer_id FROM wars WHERE \\\n            \"(attacker_id=(%s) OR defender_id=(%s)) AND peace_date IS NULL\"", "SELECT peace_offer_id FROM wars WHERE \\\n            \"(attacker=(%s) OR defender=(%s)) AND peace_date IS NULL\"")

# Line 40
content = content.replace('"(attacker_id=(%s) OR defender_id=(%s)) AND peace_date IS NULL",',
                          '"(attacker=(%s) OR defender=(%s)) AND peace_date IS NULL",')

# Line 63
content = content.replace('"p.author, u.username as author_name, w.attacker_id, "',
                          '"p.author, u.username as author_name, w.attacker, "')

content = content.replace('"w.defender_id FROM peace p "',
                          '"w.defender FROM peace p "')

# Line 164
content = content.replace('"SELECT war_id, attacker_id, defender_id FROM wars WHERE "',
                          '"SELECT id, attacker, defender FROM wars WHERE "')
content = content.replace('"(attacker_id=(%s) OR defender_id=(%s)) AND peace_offer_id=(%s) "',
                          '"(attacker=(%s) OR defender=(%s)) AND peace_offer_id=(%s) "')

# Line 292
content = content.replace('"SELECT attacker_id, defender_id FROM wars WHERE war_id=%s",',
                          '"SELECT attacker, defender FROM wars WHERE id=%s",')

# Line 310
content = content.replace('db.execute("SELECT peace_offer_id FROM wars WHERE war_id=(%s)", (war_id,))',
                          'db.execute("SELECT peace_offer_id FROM wars WHERE id=(%s)", (war_id,))')

# Line 327
content = content.replace('"UPDATE wars SET peace_offer_id=(%s) " "WHERE war_id=(%s)",',
                          '"UPDATE wars SET peace_offer_id=(%s) " "WHERE id=(%s)",')

# Line 363
content = content.replace('"SELECT war_id, attacker_id, defender_id, war_type, aggressor_message, "',
                          '"SELECT id, attacker, defender, war_type, aggressor_message, "')
content = content.replace('"defender_supplies, defender_morale FROM wars WHERE war_id=(%s)"',
                          '"defender_supplies, defender_morale FROM wars WHERE id=(%s)"')

# Line 744 / 908
content = content.replace('"WHERE ((attacker_id=%s AND defender_id=%s) "',
                          '"WHERE ((attacker=%s AND defender=%s) "')
content = content.replace('"OR (attacker_id=%s AND defender_id=%s)) "',
                          '"OR (attacker=%s AND defender=%s)) "')

# Line 743
content = content.replace('"SELECT war_type FROM wars "',
                          '"SELECT war_type FROM wars "')

# Line 907
content = content.replace('"SELECT war_id FROM wars "',
                          '"SELECT id FROM wars "')

# Line 958
content = content.replace('"SELECT MAX(peace_date) FROM wars WHERE ((attacker_id=%s "',
                          '"SELECT MAX(peace_date) FROM wars WHERE ((attacker=%s "')
content = content.replace('"AND defender_id=%s) OR (attacker_id=%s AND defender_id=%s))"',
                          '"AND defender=%s) OR (attacker=%s AND defender=%s))"')

# Line 972
content = content.replace('"INSERT INTO wars (attacker_id, defender_id, "',
                          '"INSERT INTO wars (attacker, defender, "')

# Line 1053
content = content.replace('"SELECT war_id, defender_id, attacker_id "',
                          '"SELECT id, defender, attacker "')
content = content.replace('"FROM wars WHERE (attacker_id=%s "',
                          '"FROM wars WHERE (attacker=%s "')
content = content.replace('"OR defender_id=%s) "',
                          '"OR defender=%s) "')

# Line 1075
content = content.replace('"SELECT war_id, attacker_morale, attacker_supplies, "',
                          '"SELECT id, attacker_morale, attacker_supplies, "')
content = content.replace('"FROM wars WHERE war_id IN (" + war_placeholders + ")"',
                          '"FROM wars WHERE id IN (" + war_placeholders + ")"')

# Line 1131
content = content.replace('"SELECT COUNT(attacker_id) FROM wars WHERE (defender_id=%s "',
                          '"SELECT COUNT(attacker) FROM wars WHERE (defender=%s "')
content = content.replace('"OR attacker_id=%s) AND peace_date IS NULL"',
                          '"OR attacker=%s) AND peace_date IS NULL"')

with open("wars/routes.py", "w") as f:
    f.write(content)

print("Done")
