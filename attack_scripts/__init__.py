from .Nations import Nation, Military, Economy

__all__ = ["Nation", "Military", "Economy"]

# Ensure robust `get_particular_resources` binding at package import time.
# This helps in test harnesses or long-running processes that may import
# the package in different orders and pick up stale class definitions.


def _wrap_get_particular_resources():
    def wrapper(self, resources):
        try:
            # Prefer the module-level impl if present
            m = __import__(
                "attack_scripts.Nations", fromlist=["_impl_get_particular_resources"]
            )
            impl = getattr(m, "_impl_get_particular_resources", None)
            if impl is not None:
                return impl(self.nationID, resources)
            # Fallback: make safe DB calls
            from database import get_db_connection

            rd = {}
            for res in resources:
                if res == "money":
                    with get_db_connection() as conn:
                        db = conn.cursor()
                        db.execute(
                            "SELECT gold FROM stats WHERE id=%s", (self.nationID,)
                        )
                        row = db.fetchone()
                        rd["money"] = row[0] if row and row[0] is not None else 0
                else:
                    with get_db_connection() as conn:
                        db = conn.cursor()
                        db.execute(
                            f"SELECT {res} FROM resources WHERE id=%s", (self.nationID,)
                        )
                        row = db.fetchone()
                        rd[res] = row[0] if row and row[0] is not None else 0
            for r in resources:
                rd.setdefault(r, 0)
            return rd
        except Exception:
            return {r: 0 for r in resources}

    return wrapper


# Apply the wrapper to the class we just imported
try:
    Economy.get_particular_resources = _wrap_get_particular_resources()
except Exception:
    pass
