"""XP/leveling math and role-reward application."""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import discord

from discord_bot import engagement_store as store

logger = logging.getLogger("ano_discord_bot")


def level_for_xp(xp: int) -> int:
    """Level curve: level N requires 5*N^2 + 50*N total XP (mirrors common MEE6-style curves)."""
    level = 0
    while xp >= 5 * (level + 1) ** 2 + 50 * (level + 1):
        level += 1
    return level


async def award_message_xp(member: discord.Member) -> None:
    """Award XP for a message, respecting per-user cooldown; announce + apply role reward on level-up."""
    guild_id = str(member.guild.id)
    user_id = str(member.id)
    config = store.get_level_config(guild_id)

    xp, level, last_xp_at = store.get_user_xp(guild_id, user_id)
    now = datetime.now(timezone.utc)
    if last_xp_at is not None:
        elapsed = (now - last_xp_at).total_seconds()
        if elapsed < config.xp_cooldown_seconds:
            return

    new_xp = xp + config.xp_per_message
    new_level = level_for_xp(new_xp)
    store.set_user_xp(guild_id, user_id, new_xp, new_level, now)

    if new_level > level:
        await _handle_level_up(member, config, new_level)


async def _handle_level_up(member: discord.Member, config, new_level: int) -> None:
    guild_id = str(member.guild.id)
    role_id = store.get_level_role(guild_id, new_level)
    if role_id:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role, reason=f"Reached level {new_level}")
            except discord.Forbidden:
                logger.warning("Missing permission to grant level role in guild %s", guild_id)
            except Exception as exc:
                logger.warning("Level role grant failed: %s", exc)

    if not config.level_up_enabled or not config.level_up_channel_id:
        return
    channel = member.guild.get_channel(int(config.level_up_channel_id))
    if channel:
        try:
            await channel.send(f"🎉 {member.mention} just reached **level {new_level}**!")
        except discord.Forbidden:
            logger.warning("Missing permission to post level-up message in guild %s", guild_id)
