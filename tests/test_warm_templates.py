"""Boot-time warm-up must compile templates and never raise."""
import app as app_module


def test_warm_up_compiles_templates_and_does_not_raise(caplog):
    flask_app = app_module.app
    flask_app.jinja_env.cache.clear() if flask_app.jinja_env.cache else None
    app_module._warm_templates_and_imports(flask_app)
    assert flask_app.jinja_env.cache is None or len(flask_app.jinja_env.cache) > 0
