# Local shim to provide ThreadedConnectionPool when psycopg2 lacks .pool
# This is ONLY for local testing environments where a compiled psycopg2 package
# may not expose `pool`. It is safe to keep in repo - it only activates when
# `psycopg2` exists and doesn't already have `pool`.
try:
    import os
    import types
    import psycopg2

    if not hasattr(psycopg2, "pool"):

        class PoolShim:
            def __init__(self, minconn, maxconn, **kwargs):
                self.minconn = minconn
                self.maxconn = maxconn

            def getconn(self):
                return psycopg2.connect(
                    database=os.getenv("PG_DATABASE"),
                    user=os.getenv("PG_USER"),
                    password=os.getenv("PG_PASSWORD"),
                    host=os.getenv("PG_HOST"),
                    port=os.getenv("PG_PORT"),
                    connect_timeout=10,
                )

            def putconn(self, conn, close=False):
                try:
                    conn.close()
                except Exception:
                    pass

            def closeall(self):
                pass

        psycopg2.pool = types.SimpleNamespace(ThreadedConnectionPool=PoolShim)
except Exception:
    # Best-effort shim; don't raise on import
    pass
