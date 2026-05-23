"""Entry point: python -m discord_bot.main"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from discord_bot.backend import backend_mode_label, get_backend
from discord_bot.commands import admin_cmds
from discord_bot.commands import guild_setup as guild_setup_cmds
from discord_bot.commands import info as info_cmds
from discord_bot.commands import register as register_cmds
from discord_bot.config import DISCORD_BOT_TOKEN, validate_config
from discord_bot.embeds import EMBED_UI_VERSION
from discord_bot.panel_service import refresh_all_guild_panels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ano_discord_bot")


class AnOBot(commands.Bot):
    def __init__(self, backend) -> None:
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix="!", intents=intents)
        self.backend = backend

    async def setup_hook(self) -> None:
        register_cmds.register_commands(self.tree, self.backend)
        info_cmds.register_commands(self.tree, self.backend)
        guild_setup_cmds.register_commands(self.tree)
        admin_cmds.register_commands(self.tree, self.backend)
        synced = await self.tree.sync()
        logger.info("Synced %s global slash command(s)", len(synced))

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (%s); data mode=%s; embed_ui=%s",
            self.user,
            self.user.id if self.user else "?",
            backend_mode_label(),
            EMBED_UI_VERSION,
        )
        if not self.panel_refresh_loop.is_running():
            self.panel_refresh_loop.start()

    @tasks.loop(minutes=15)
    async def panel_refresh_loop(self) -> None:
        await refresh_all_guild_panels(self)

    @panel_refresh_loop.before_loop
    async def before_panel_refresh(self) -> None:
        await self.wait_until_ready()


def main() -> None:
    validate_config()
    if __import__("discord_bot.backend", fromlist=["_has_database_url"])._has_database_url():
        try:
            from database import ensure_schema_compat

            ensure_schema_compat()
        except Exception as exc:
            logger.warning("ensure_schema_compat: %s", exc)
    backend = get_backend()
    logger.info("Starting AnO Discord bot (mode=%s)", backend_mode_label())
    bot = AnOBot(backend)
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
