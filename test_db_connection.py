#!/usr/bin/env python3
"""
Test database connection with current environment variables
Run this locally to verify DATABASE_URL is correct before deploying
"""
import os
import psycopg2
from urllib.parse import urlparse

# Load from .env if present
from dotenv import load_dotenv

load_dotenv()


def test_connection():
    """Test database connection using DATABASE_URL or DATABASE_PUBLIC_URL"""

    # Check which URL is available
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")

    if not db_url:
        print("❌ ERROR: No DATABASE_URL or DATABASE_PUBLIC_URL found in environment")
        print("\nSet one of these environment variables:")
        print("  export DATABASE_URL='postgresql://user:password@host:port/database'")
        return False

    print(f"🔍 Testing connection using: {db_url.split('@')[0]}@****")

    # Parse the URL
    parsed = urlparse(db_url)

    print("\nConnection details:")
    print(f"  Host: {parsed.hostname}")
    print(f"  Port: {parsed.port or 5432}")
    print(f"  User: {parsed.username}")
    print(f"  Database: {parsed.path[1:] if parsed.path else 'postgres'}")
    print(f"  Password: {'*' * len(parsed.password) if parsed.password else '(empty)'}")

    try:
        # Attempt connection
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path[1:] if parsed.path else "postgres",
            connect_timeout=10,
        )

        # Test query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        print("\n✅ SUCCESS: Connection established!")
        print(f"PostgreSQL version: {version[:50]}...")
        return True

    except psycopg2.OperationalError as e:
        print("\n❌ ERROR: Connection failed!")
        print(f"Error: {e}")

        if "password authentication failed" in str(e):
            print("\n🔧 Fix: The password is incorrect.")
            print("   1. Get the correct DATABASE_URL from Railway dashboard")
            print("   2. Update your .env file or Railway environment variables")
            print("   3. Redeploy if on Railway")
        elif "could not connect" in str(e) or "could not translate" in str(e):
            print("\n🔧 Fix: Cannot reach the database host.")
            print("   1. Check if the host is accessible from your network")
            print("   2. For Railway, use DATABASE_PUBLIC_URL for external access")
            print("   3. DATABASE_URL only works within Railway's private network")

        return False

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Database Connection Test")
    print("=" * 60)

    success = test_connection()

    print("\n" + "=" * 60)
    exit(0 if success else 1)
