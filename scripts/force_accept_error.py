"""Force a server 500 in accept_trade by monkeypatching give_resource to raise.
This runs against local app test client (no production changes) and prints the error page and generated error id.
"""

import re
from app import app
from database import get_db_connection

# Create a trade we can accept
with get_db_connection() as conn:
    db = conn.cursor()
    # ensure canonical users exist
    db.execute(
        "INSERT INTO users (username, email, date, hash) VALUES (%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING",
        ("test_integration", "test_integration@example.com", "2026-01-01", ""),
    )
    db.execute("SELECT id FROM users WHERE username=%s", ("test_integration",))
    offerer = db.fetchone()[0]
    # use Lamlor uid if present, else fallback to 781
    db.execute("SELECT id FROM users WHERE username=%s", ("Lamlor",))
    row = db.fetchone()
    offeree = row[0] if row else 781
    # create a buy offer: buyer=test_integration buying from Lamlor (offeree)
    db.execute(
        "INSERT INTO trades (offerer, type, resource, amount, price, offeree) VALUES (%s,%s,%s,%s,%s,%s) RETURNING offer_id",
        (offerer, "buy", "coal", 5, 10, offeree),
    )
    trade_id = db.fetchone()[0]
    conn.commit()

print("Created trade id", trade_id, "offerer", offerer, "offeree", offeree)

# Now perform the accept under a monkeypatched give_resource that raises
import market

orig_give = market.give_resource


def failing_give_resource(giver_id, taker_id, resource, amount):
    raise Exception("simulated give_resource failure")


market.give_resource = failing_give_resource

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess["user_id"] = offeree

    resp = client.post(f"/accept_trade/{trade_id}", follow_redirects=True)
    print("status", resp.status_code)
    text = resp.get_data(as_text=True)
    # extract error id if present
    m = re.search(r"([a-z0-9]{20}-\d{9,})", text)
    if m:
        print("Found error id in page:", m.group(1))
    else:
        print("No error id found in response")
    # Print small snippet of the page
    start = text.find('<div class="templatedivcontent">')
    if start != -1:
        print(text[start : start + 600])
    else:
        print(text[:600])

# Restore original function and clean up the created trade (if still present)
market.give_resource = orig_give
with get_db_connection() as conn:
    db = conn.cursor()
    db.execute("DELETE FROM trades WHERE offer_id=%s", (trade_id,))
    conn.commit()
print("Cleanup done")
