"""AI-run "bot nations": always-available war targets with real armies/economies.

Bots are ordinary rows in ``users`` (``auth_type = 'bot'``) so every game system
treats them like a nation, plus a ``bot_nations`` profile row. They never log in,
never declare war, and fight back automatically (see ``war_ai``).
"""

BOT_AUTH_TYPE = "bot"
