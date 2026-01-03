#!/usr/bin/env python3
"""Quick script to rename bot nation usernames in the database."""

from database import get_db_cursor

try:
    with get_db_cursor() as db:
        db.execute("UPDATE users SET username = %s WHERE id = %s", ("Market Bot", 9999))
        db.execute("UPDATE users SET username = %s WHERE id = %s", ("Supply Bot", 9998))
        print("✓ Bot names updated successfully")
        print("  Bot 9999: Market Bot")
        print("  Bot 9998: Supply Bot")
except Exception as e:
    print(f"✗ Error updating bot names: {e}")
