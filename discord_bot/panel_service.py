"""Post and refresh pinned-style panel messages in configured guild channels."""


import logging
from typing import Optional

import discord

from discord_bot.guild_store import (
    PANEL_KEYS,
    get_guild_settings,
    get_panel_message_id,
    list_configured_guild_ids,
    save_panel_message,
)
from discord_bot.panels.builders import PANEL_BUILDERS

logger = logging.getLogger(__name__)


async def refresh_guild_panels(
    bot: discord.Client,
    guild_id: int,
    *,
    channel: Optional[discord.abc.Messageable] = None,
) -> int:
    """Update or create all bound panels for a guild. Returns count refreshed."""
    settings = get_guild_settings(str(guild_id))
    if not settings or not settings.panels_enabled:
        return 0
    guild = bot.get_guild(guild_id)
    if not guild:
        return 0

    refreshed = 0
    for key in PANEL_KEYS:
        channel_id = settings.panel_channels.get(key)
        if not channel_id:
            continue
        ch = guild.get_channel(int(channel_id))
        if ch is None or not hasattr(ch, "send"):
            logger.warning("Panel %s channel %s missing in guild %s", key, channel_id, guild_id)
            continue
        builder = PANEL_BUILDERS.get(key)
        if not builder:
            continue
        embed = builder()
        msg_id = get_panel_message_id(str(guild_id), key)
        try:
            if msg_id:
                msg = await ch.fetch_message(int(msg_id))
                await msg.edit(embed=embed, content=None)
            else:
                msg = await ch.send(embed=embed)
                await msg.pin()
                save_panel_message(str(guild_id), key, str(ch.id), str(msg.id))
            refreshed += 1
        except discord.NotFound:
            msg = await ch.send(embed=embed)
            try:
                await msg.pin()
            except discord.HTTPException:
                pass
            save_panel_message(str(guild_id), key, str(ch.id), str(msg.id))
            refreshed += 1
        except Exception as exc:
            logger.warning(
                "Panel refresh failed guild=%s panel=%s: %s", guild_id, key, exc
            )
    return refreshed


async def refresh_all_guild_panels(bot: discord.Client) -> None:
    for gid in list_configured_guild_ids():
        try:
            count = await refresh_guild_panels(bot, int(gid))
            if count:
                logger.info("Refreshed %s panel(s) for guild %s", count, gid)
        except Exception as exc:
            logger.warning("Guild panel refresh failed for %s: %s", gid, exc)
