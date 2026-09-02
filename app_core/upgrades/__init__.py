# Deliberately does NOT import .routes here (unlike most app_core/<feature>
# packages' __init__.py). A parent package's __init__.py always runs first,
# even for `from app_core.upgrades.services import get_upgrades` - so an
# eager `from .routes import bp` here would force every caller of
# get_upgrades() (including Celery-context code in attack_scripts/*) to also
# construct routes.py's Blueprint and pull in its action_loop.py/helpers.py
# imports, for no reason. app.py imports bp directly from .routes instead:
# `from app_core.upgrades.routes import bp`.
