from src.app import app


def test_app_has_limiter_attribute():
    # We assert the attribute exists (could be None when limiter not installed)
    assert hasattr(app, "limiter")
    # It should explicitly be None or have an attribute 'limit' when available
    limiter = app.limiter
    if limiter is not None:
        assert hasattr(limiter, "limit")
