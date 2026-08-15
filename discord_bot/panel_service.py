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
from discord_bot.panels.builders import ANALYTICS_CHART_FILENAME, PANEL_BUILDERS, PANEL_FILE_BUILDERS

logger = logging.getLogger(__name__)


import asyncio

async def refresh_guild_panels(
    bot: discord.Client,
    guild_id: int,
    *,
    channel: Optional[discord.abc.Messageable] = None,
) -> int:
    """Update or create all bound panels for a guild. Returns count refreshed."""
    settings = await asyncio.to_thread(get_guild_settings, str(guild_id))
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
        file_builder = PANEL_FILE_BUILDERS.get(key)
        if file_builder:
            embed, chart_buf = file_builder()
        else:
            builder = PANEL_BUILDERS.get(key)
            if not builder:
                continue
            embed = builder()
            chart_buf = None

        def _make_file() -> Optional[discord.File]:
            if chart_buf is None:
                return None
            chart_buf.seek(0)
            return discord.File(chart_buf, filename=ANALYTICS_CHART_FILENAME)

        msg_id = await asyncio.to_thread(get_panel_message_id, str(guild_id), key)
        try:
            if msg_id:
                msg = await ch.fetch_message(int(msg_id))
                file = _make_file()
                if file is not None:
                    await msg.edit(embed=embed, content=None, attachments=[file])
                else:
                    await msg.edit(embed=embed, content=None)
            else:
                file = _make_file()
                msg = await ch.send(embed=embed, file=file) if file is not None else await ch.send(embed=embed)
                await msg.pin()
                await asyncio.to_thread(save_panel_message, str(guild_id), key, str(ch.id), str(msg.id))
            refreshed += 1
        except discord.NotFound:
            file = _make_file()
            msg = await ch.send(embed=embed, file=file) if file is not None else await ch.send(embed=embed)
            try:
                await msg.pin()
            except discord.HTTPException:
                pass
            await asyncio.to_thread(save_panel_message, str(guild_id), key, str(ch.id), str(msg.id))
            refreshed += 1
        except Exception as exc:
            logger.warning(
                "Panel refresh failed guild=%s panel=%s: %s", guild_id, key, exc
            )
    return refreshed


async def refresh_all_guild_panels(bot: discord.Client) -> None:
    guild_ids = await asyncio.to_thread(list_configured_guild_ids)
    for gid in guild_ids:
        try:
            count = await refresh_guild_panels(bot, int(gid))
            if count:
                logger.info("Refreshed %s panel(s) for guild %s", count, gid)
        except Exception as exc:
            logger.warning("Guild panel refresh failed for %s: %s", gid, exc)
