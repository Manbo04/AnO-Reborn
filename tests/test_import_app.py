def test_import_app():
    """Smoke test to ensure the Flask app imports without runtime errors."""
    import app as application_module

    assert hasattr(application_module, "app")

    from flask import Flask

    assert isinstance(application_module.app, Flask)
