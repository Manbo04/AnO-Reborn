"""Simple diagnostic script to test DB connectivity and print environment info.

Run this locally or in the deployment container to get immediate, actionable
errors (DNS resolution, auth errors, timeouts).
"""
import os
import sys
import traceback
import psycopg2
import socket


def masked(s):
    if not s:
        return ""
    return s if len(s) < 6 else s[:2] + "***" + s[-2:]


def print_env():
    print("DATABASE diagnostics")
    keys = [
        "DATABASE_URL",
        "DATABASE_PUBLIC_URL",
        "PG_HOST",
        "PG_PORT",
        "PG_USER",
        "PG_DATABASE",
        "PG_PASSWORD",
    ]
    for k in keys:
        v = os.getenv(k)
        if k == "PG_PASSWORD":
            v = masked(v)
        print(f"{k}: {v}")


def try_connect(timeout=10):
    params = dict(
        database=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        connect_timeout=timeout,
    )
    print(
        "Trying to connect with params:",
        {k: (v if k != "password" else masked(v)) for k, v in params.items()},
    )
    # DNS / socket level check
    host = params.get("host") or "localhost"
    port = int(params.get("port") or 5432)
    print(f"Resolving host {host}...")
    try:
        addrs = socket.getaddrinfo(host, port)
        print("Host resolved to:")
        for a in addrs:
            print(" ", a[4])
    except Exception as e:
        print("DNS resolution failed:", e)

    print(f"Attempting TCP connect to {host}:{port} with timeout={timeout}s...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        print("TCP connect succeeded")
    except Exception as e:
        print("TCP connect failed:", e)

    try:
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        print("Connected OK, SELECT 1 ->", cur.fetchone())
        cur.close()
        conn.close()
        return 0
    except Exception:
        print("Connection FAILED at psycopg2:")
        traceback.print_exc()
        return 2


def main():
    print_env()
    return try_connect()


if __name__ == "__main__":
    sys.exit(main())
