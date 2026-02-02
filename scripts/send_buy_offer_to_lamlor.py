"""Create a buy market trade (offer) from the canonical account to user Lamlor.

Usage: python scripts/send_buy_offer_to_lamlor.py [--amount AMOUNT] [--price PRICE]
Defaults: amount=10, price=10

This script is conservative: it will upsert the canonical account, top up gold if needed,
create the trade row and print the resulting trade id and acceptance URL.
"""

import argparse
from database import get_db_connection

parser = argparse.ArgumentParser()
parser.add_argument("--amount", type=int, default=10)
parser.add_argument("--price", type=int, default=10)
args = parser.parse_args()

AMOUNT = args.amount
PRICE = args.price
RESOURCE = "coal"
CANON = "test_integration"
LAMLOR_USERNAMES = ["Lamlor", "lamlor", "lamlor_t"]
FALLBACK_UID = 781

with get_db_connection() as conn:
    db = conn.cursor()
    # Find Lamlor by username (case-insensitive), fallback to known id
    found = False
    for u in LAMLOR_USERNAMES:
        db.execute("SELECT id FROM users WHERE username=%s", (u,))
        r = db.fetchone()
        if r:
            offeree = r[0]
            found = True
            break
    if not found:
        # Try case-insensitive search
        db.execute(
            "SELECT id FROM users WHERE lower(username)=%s",
            (LAMLOR_USERNAMES[0].lower(),),
        )
        r = db.fetchone()
        if r:
            offeree = r[0]
            found = True
    if not found:
        print(
            f"Could not find user Lamlor by username; falling back to uid {FALLBACK_UID}"
        )
        offeree = FALLBACK_UID

    # Ensure canonical offerer exists
    db.execute(
        "INSERT INTO users (username, email, date, hash) VALUES (%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING",
        (CANON, f"{CANON}@example.com", "2026-01-01", ""),
    )
    db.execute("SELECT id FROM users WHERE username=%s", (CANON,))
    offerer = db.fetchone()[0]

    # Ensure offerer has enough gold; top up to a safe value if not
    total_cost = AMOUNT * PRICE
    db.execute("SELECT gold FROM stats WHERE id=%s", (offerer,))
    r = db.fetchone()
    if not r:
        db.execute(
            "INSERT INTO stats (id, gold, location) VALUES (%s, %s, %s)",
            (offerer, total_cost + 1000, "Test"),
        )
        conn.commit()
        current_gold = total_cost + 1000
    else:
        current_gold = int(r[0] or 0)
        if current_gold < total_cost:
            print(f"Topping up {CANON} gold from {current_gold} to {total_cost + 1000}")
            db.execute(
                "UPDATE stats SET gold=%s WHERE id=%s", (total_cost + 1000, offerer)
            )
            conn.commit()
            current_gold = total_cost + 1000

    # Insert the trade (type=buy) and debit the offerer
    db.execute(
        "INSERT INTO trades (offerer, type, resource, amount, price, offeree) VALUES (%s,%s,%s,%s,%s,%s) RETURNING offer_id",
        (offerer, "buy", RESOURCE, AMOUNT, PRICE, offeree),
    )
    trade_id = db.fetchone()[0]

    db.execute("UPDATE stats SET gold = gold - %s WHERE id=%s", (total_cost, offerer))
    conn.commit()

print(
    f"Created buy offer id={trade_id} from {CANON} (id={offerer}) to user id={offeree}: buy {AMOUNT} {RESOURCE} @ {PRICE} each (total {total_cost})"
)
print(f"Offeree should see it on their country page: /country/id={offeree}")
print(f"Accept endpoint (for offeree to POST): /accept_trade/{trade_id}")
