#!/usr/bin/env python3
"""
Direct database password reset - works without Flask import
"""

import bcrypt
import os
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2

load_dotenv()

username = "Dede"
new_password = "Manbo0822131619"

# Try to use Railway DATABASE_URL first, fallback to local config
database_url = os.getenv("DATABASE_URL")

if database_url:
    # Railway environment - parse the DATABASE_URL
    parsed = urlparse(database_url)
    db_config = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path[1:] if parsed.path else "railway"
    }
    print(f"Using Railway database: {parsed.hostname}")
else:
    # Local environment
    db_config = {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
        "database": os.getenv("PG_DATABASE", "postgres")
    }
    print(f"Using local database: {db_config['host']}")

# Hash the new password
hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

try:
    print(f"Attempting to connect to {db_config['host']}:{db_config['port']}/{db_config['database']}...")
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    
    # Check if user exists
    cur.execute("SELECT id, username FROM users WHERE username=(%s)", (username,))
    user = cur.fetchone()
    
    if not user:
        print(f"✗ Error: User '{username}' not found")
    else:
        user_id, db_username = user
        
        # Update password
        cur.execute("UPDATE users SET password=(%s) WHERE id=(%s)", (hashed_pw, user_id))
        conn.commit()
        
        print(f"✓ Password reset successful!")
        print(f"✓ Username: {username} (ID: {user_id})")
        print(f"✓ New password: {new_password}")
        print("\nYou can now log in at https://affairsandorder.com with these credentials.")
        
    cur.close()
    conn.close()
    
except psycopg2.OperationalError as e:
    print(f"✗ Cannot connect to database: {e}")
    print("\nTroubleshooting:")
    print("- Check that DATABASE_URL is set (railway run should have it)")
    print("- Or ensure local PostgreSQL is running on port 5433")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
