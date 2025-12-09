#!/usr/bin/env python3
"""
Admin script to reset a user's password
Usage: python3 admin_reset_password.py <username> <new_password>
"""

import sys
import bcrypt
import os
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2

load_dotenv()

def get_db_connection():
    """Get database connection from Railway DATABASE_URL or local config"""
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        parsed = urlparse(database_url)
        return psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path[1:]
        )
    else:
        # Fallback to local env variables
        return psycopg2.connect(
            host=os.getenv("PG_HOST", "localhost"),
            port=os.getenv("PG_PORT", "5432"),
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", ""),
            database=os.getenv("PG_DATABASE", "postgres")
        )

def reset_password(username, new_password):
    """Reset a user's password"""
    
    if not username or not new_password:
        print("Error: Username and password required")
        print("Usage: python admin_reset_password.py <username> <new_password>")
        return False
    
    # Hash the new password
    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if user exists
        cur.execute("SELECT id, username FROM users WHERE username=(%s)", (username,))
        user = cur.fetchone()
        
        if not user:
            print(f"Error: User '{username}' not found")
            cur.close()
            conn.close()
            return False
        
        user_id, db_username = user
        
        # Update password
        cur.execute("UPDATE users SET password=(%s) WHERE id=(%s)", (hashed_pw, user_id))
        conn.commit()
        
        print(f"✓ Password reset successful for user '{username}' (ID: {user_id})")
        print(f"✓ New password: {new_password}")
        
        cur.close()
        conn.close()
        return True
            
    except Exception as e:
        print(f"Error resetting password: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python admin_reset_password.py <username> <new_password>")
        sys.exit(1)
    
    username = sys.argv[1]
    new_password = sys.argv[2]
    
    if reset_password(username, new_password):
        sys.exit(0)
    else:
        sys.exit(1)
