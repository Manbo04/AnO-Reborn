"""Entry point: python -m discord_bot.main"""


import asyncio
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

# Map channel name substrings → panel keys (order matters: first match wins)
_CHANNEL_PANEL_MAP = [
    ("bot-guide",        "readme"),
    ("influence-board",  "leaderboard"),
    ("war-feed",         "war_feed"),
    ("nation-inspector", "inspector"),
    ("global-affairs",   "world_status"),
    ("realm-alerts",     "alerts"),
]


async def _auto_bind_panels(bot: "AnOBot", guild: discord.Guild) -> None:
    """Bind panel channels by name convention if no bindings exist yet."""
    from discord_bot.guild_store import (
        bind_panel_channel,
        get_guild_settings,
    )

    settings = await asyncio.to_thread(get_guild_settings, str(guild.id))
    if settings and settings.panel_channels:
        return  # already configured

    bound = 0
    for ch in guild.text_channels:
        name = ch.name.lower()
        for fragment, panel_key in _CHANNEL_PANEL_MAP:
            if fragment in name:
                try:
                    await asyncio.to_thread(
                        bind_panel_channel, str(guild.id), panel_key, str(ch.id)
                    )
                    logger.info(
                        "Auto-bound panel '%s' → #%s (%s)", panel_key, ch.name, ch.id
                    )
                    bound += 1
                except Exception as exc:
                    logger.warning("Auto-bind %s failed: %s", panel_key, exc)
                break

    if bound:
        logger.info("Auto-configured %d panel(s) for guild %s (%s)", bound, guild.name, guild.id)


# Channel name fragments that should be visible to Certified Human (excludes staff)
_PUBLIC_PANEL_FRAGMENTS = {
    "bot-guide", "influence-board", "war-feed",
    "nation-inspector", "global-affairs", "realm-alerts",
}


async def _setup_panel_permissions(guild: discord.Guild) -> None:
    """Grant VIEW_CHANNEL to Certified Human role for all public panel channels."""
    certified_human = discord.utils.find(
        lambda r: "certified human" in r.name.lower(), guild.roles
    )
    if not certified_human:
        logger.info("No 'Certified Human' role found in %s — skipping permission setup", guild.name)
        return

    for ch in guild.text_channels:
        name = ch.name.lower()
        if not any(frag in name for frag in _PUBLIC_PANEL_FRAGMENTS):
            continue
        overwrite = ch.overwrites_for(certified_human)
        if overwrite.view_channel is True:
            continue  # already set
        overwrite.view_channel = True
        try:
            await ch.set_permissions(certified_human, overwrite=overwrite)
            logger.info("Granted VIEW_CHANNEL to Certified Human for #%s", ch.name)
        except discord.Forbidden:
            logger.warning("Missing permissions to edit #%s — grant Manage Channels to bot", ch.name)
        except Exception as exc:
            logger.warning("Permission setup failed for #%s: %s", ch.name, exc)


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
        for guild in self.guilds:
            try:
                await _auto_bind_panels(self, guild)
            except Exception as exc:
                logger.warning("Auto-bind failed for guild %s: %s", guild.id, exc)
            try:
                await _setup_panel_permissions(guild)
            except Exception as exc:
                logger.warning("Permission setup failed for guild %s: %s", guild.id, exc)
        if not self.panel_refresh_loop.is_running():
            self.panel_refresh_loop.start()

    @tasks.loop(minutes=1)
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
        try:
            from bot_api import warmup_bot_api

            warmup_bot_api()
        except Exception as exc:
            logger.warning("warmup_bot_api: %s", exc)
    backend = get_backend()
    logger.info("Starting AnO Discord bot (mode=%s)", backend_mode_label())
    bot = AnOBot(backend)
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
