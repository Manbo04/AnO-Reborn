def __getattr__(name):
    if name in ("Nation", "Military", "Economy"):
        from .Nations import Nation, Military, Economy
        globals()["Nation"] = Nation
        globals()["Military"] = Military
        globals()["Economy"] = Economy
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["Nation", "Military", "Economy"]
