def __getattr__(name):
    if name == "bp":
        from .routes import bp
        globals()["bp"] = bp
        return bp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["bp"]
