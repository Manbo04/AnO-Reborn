#!/usr/bin/env python3
"""
Fix script to update existing provinces with better default values for
happiness, productivity, and consumer_spending.
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def fix_province_defaults():
    try:
        # Use DATABASE_URL if available, otherwise build from env vars
        database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
        
        if not database_url:
            print("ERROR: DATABASE_URL not set")
            return False
        
        conn = psycopg2.connect(database_url)
        db = conn.cursor()
        
        # Update happiness from 0 to 50
        db.execute("UPDATE provinces SET happiness=50 WHERE happiness=0")
        happiness_updated = db.rowcount
        
        # Update productivity from 0 to 50
        db.execute("UPDATE provinces SET productivity=50 WHERE productivity=0")
        productivity_updated = db.rowcount
        
        # Update consumer_spending from 0 to 50
        db.execute("UPDATE provinces SET consumer_spending=50 WHERE consumer_spending=0")
        consumer_spending_updated = db.rowcount
        
        conn.commit()
        
        print(f"✓ Updated {happiness_updated} provinces - happiness 0→50")
        print(f"✓ Updated {productivity_updated} provinces - productivity 0→50")
        print(f"✓ Updated {consumer_spending_updated} provinces - consumer_spending 0→50")
        
        db.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    success = fix_province_defaults()
    exit(0 if success else 1)
