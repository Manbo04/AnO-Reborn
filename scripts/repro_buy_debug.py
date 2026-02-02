from app import app
from database import get_db_connection
import re

# Setup user/province similar to test
canonical_username = "test_integration"
with get_db_connection() as conn:
    db = conn.cursor()
    db.execute(
        "INSERT INTO users (username, email, date, hash) VALUES (%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING",
        (canonical_username, f"{canonical_username}@example.com", "2026-01-01", ""),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (canonical_username,))
    uid = db.fetchone()[0]
    db.execute(
        "SELECT id FROM provinces WHERE userId=%s AND provincename=%s", (uid, "PA")
    )
    row = db.fetchone()
    if row:
        pid = row[0]
    else:
        db.execute(
            "INSERT INTO provinces (userId, provincename, citycount, land, population) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (uid, "PA", 1, 1, 100000),
        )
        pid = db.fetchone()[0]
    db.execute(
        "INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (pid,)
    )
    db.execute(
        "INSERT INTO stats (id, location, gold) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET location=%s, gold=%s",
        (uid, "Test", 1000000, "Test", 1000000),
    )
    db.execute(
        "INSERT INTO resources (id, consumer_goods, rations, steel, aluminium) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET consumer_goods=%s, rations=%s, steel=%s, aluminium=%s",
        (uid, 0, 0, 100, 100, 0, 0, 100, 100),
    )
    conn.commit()

with get_db_connection() as conn:
    db = conn.cursor()
    db.execute(
        "UPDATE resources SET steel=%s, aluminium=%s WHERE id=%s",
        (1000000000, 1000000000, uid),
    )
    db.execute("UPDATE stats SET gold=%s WHERE id=%s", (1000000000, uid))
    conn.commit()

client = app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = uid

resp = client.post(
    f"/buy/gas_stations/{pid}", data={"gas_stations": 1}, follow_redirects=True
)
print("status", resp.status_code)
text = resp.get_data(as_text=True)

# try extracting the message
m = re.search(r'<p class="landingpagecontent center">\s*([^<]+?)\s*</p>', text)
if m:
    print("message:", m.group(1))
else:
    print("could not find message; printing full body below:\n")
    print(text)
