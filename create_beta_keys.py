#!/usr/bin/env python3
"""
Script to create the beta_keys table and insert 100 beta keys into the database
"""

import os
import psycopg2
from dotenv import load_dotenv
import secrets
import string

load_dotenv()

# Database connection
conn = psycopg2.connect(
    database=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT")
)

db = conn.cursor()

# Create keys table if it doesn't exist
print("Creating 'keys' table...")
db.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        id SERIAL PRIMARY KEY,
        key VARCHAR(255) UNIQUE NOT NULL,
        used BOOLEAN DEFAULT FALSE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        used_at TIMESTAMP NULL
    )
""")

# Generate 100 unique keys
print("Generating 100 beta keys...")
keys = []
for i in range(100):
    key = '-'.join(''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)) for _ in range(4))
    keys.append(key)

# Insert keys into database
print("Inserting keys into database...")
for key in keys:
    try:
        db.execute("INSERT INTO keys (key, used) VALUES (%s, FALSE)", (key,))
    except psycopg2.IntegrityError:
        # Key already exists, skip it
        conn.rollback()
        continue

conn.commit()

# Verify insertion
db.execute("SELECT COUNT(*) FROM keys WHERE used = FALSE")
count = db.fetchone()[0]
print(f"✅ Successfully created {count} available beta keys")

# Print all available keys
db.execute("SELECT key FROM keys WHERE used = FALSE ORDER BY id")
available_keys = db.fetchall()
print("\n" + "="*50)
print("AVAILABLE BETA KEYS:")
print("="*50 + "\n")

for i, (key,) in enumerate(available_keys, 1):
    print(f"{i}. {key}")

db.close()
conn.close()
