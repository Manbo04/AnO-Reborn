#!/usr/bin/env python3
"""
Direct database password reset - works without Flask import
"""

import bcrypt
import os
import logging
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2

load_dotenv()

# Configuration: change these values as needed
username = os.getenv('RESET_PW_USERNAME', 'Dede')
new_password = os.getenv('RESET_PW_NEW_PASSWORD', None)

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
    logging.getLogger(__name__).info("Using Railway database: %s", parsed.hostname)
else:
    # Local environment
    db_config = {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
        "database": os.getenv("PG_DATABASE", "postgres")
    }
    logging.getLogger(__name__).info("Using local database: %s", db_config['host'])

if not new_password:
    logging.getLogger(__name__).error('No new password specified. Set RESET_PW_NEW_PASSWORD env var to proceed.')
    raise SystemExit(1)

# Hash the new password (store as utf-8 string to be consistent with signup flow)
hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

try:
    logging.getLogger(__name__).info("Attempting to connect to %s:%s/%s...", db_config['host'], db_config['port'], db_config['database'])
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Check if user exists
    cur.execute("SELECT id, username FROM users WHERE username=(%s)", (username,))
    user = cur.fetchone()

    if not user:
        logging.getLogger(__name__).warning("User '%s' not found", username)
    else:
        user_id, db_username = user

        # Update hashed password in `hash` column (consistent with signup flow)
        cur.execute("UPDATE users SET hash=(%s) WHERE id=(%s)", (hashed_pw, user_id))
        conn.commit()

        logging.getLogger(__name__).info("Password reset successful for user %s (ID: %s)", username, user_id)

    cur.close()
    conn.close()

except psycopg2.OperationalError as e:
    logging.getLogger(__name__).error("Cannot connect to database: %s", e)
    logging.getLogger(__name__).info("Troubleshooting: ensure DATABASE_URL is set or local DB is running and accessible")
    raise
except Exception:
    logging.getLogger(__name__).exception("Unexpected error while resetting password")
    raise
