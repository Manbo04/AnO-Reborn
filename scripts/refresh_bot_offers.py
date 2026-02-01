#!/usr/bin/env python3
"""
Refresh bot market offers for essential resources.
This script should be run daily to maintain supply of consumer goods and rations.
"""

from database import get_db_connection

BOT_USER_ID = 9999  # Market Bot

# Define the bot offers to maintain
BOT_OFFERS = [
    # (type, resource, amount, price)
    ("sell", "consumer_goods", 100000, 50),  # 100k consumer goods @ 50 gold
    ("sell", "rations", 100000, 100),  # 100k rations @ 100 gold
]


def refresh_bot_offers():
    """Delete old bot offers and create fresh ones."""
    with get_db_connection() as conn:
        db = conn.cursor()

        for offer_type, resource, amount, price in BOT_OFFERS:
            # Delete existing bot offers for this resource/type combo
            db.execute(
                "DELETE FROM offers WHERE user_id = %s AND resource = %s AND type = %s",
                (BOT_USER_ID, resource, offer_type),
            )

            # Insert fresh offer
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) "
                "VALUES (%s, %s, %s, %s, %s)",
                (BOT_USER_ID, offer_type, resource, amount, price),
            )
            print(f"Created {offer_type} offer: {amount:,} {resource} @ {price} gold")

        conn.commit()
        print("Bot offers refreshed successfully!")


if __name__ == "__main__":
    refresh_bot_offers()
