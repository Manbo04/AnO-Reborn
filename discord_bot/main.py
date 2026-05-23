"""Entry point: python -m discord_bot.main"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from discord_bot.api import BotApiClient
from discord_bot.commands import info as info_cmds
from discord_bot.commands import register as register_cmds
from discord_bot.config import DISCORD_BOT_TOKEN, validate_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ano_discord_bot")


class AnOBot(commands.Bot):
    def __init__(self, api: BotApiClient) -> None:
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix="!", intents=intents)
        self.api = api

    async def setup_hook(self) -> None:
        register_cmds.register_commands(self.tree, self.api)
        info_cmds.register_commands(self.tree, self.api)
        synced = await self.tree.sync()
        logger.info("Synced %s global slash command(s)", len(synced))


def main() -> None:
    validate_config()
    api = BotApiClient()
    bot = AnOBot(api)
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
