"""Event handler logic for server logging: message edits/deletes, member and
role/channel changes — posted as embeds to a per-guild configurable log channel.

Known limitation: Discord fires the same on_member_remove for both voluntary
leaves and kicks (no distinct "kick" event), so a kicked member shows up here
as "member left" in addition to the explicit case-log embed /kick posts to
the moderation log channel (see moderation_listeners.py). Disambiguating via
an audit-log lookback is future work, not required for this feature.
"""

import logging
from typing import Optional

import discord

from discord_bot import logging_store as store

logger = logging.getLogger("ano_discord_bot")


def _get_log_channel(guild: discord.Guild, config) -> Optional[discord.TextChannel]:
    if not config.log_channel_id:
        return None
    channel = guild.get_channel(int(config.log_channel_id))
    return channel if isinstance(channel, discord.TextChannel) else None


async def _post(guild: discord.Guild, config, embed: discord.Embed) -> None:
    channel = _get_log_channel(guild, config)
    if not channel:
        return
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        logger.warning("Missing permission to post log embed in guild %s", guild.id)
    except Exception as exc:
        logger.warning("Log embed post failed in guild %s: %s", guild.id, exc)


async def handle_message_edit(before: discord.Message, after: discord.Message) -> None:
    if not after.guild or after.author.bot:
        return
    if before.content == after.content:
        return  # e.g. an embed-only edit (link unfurl) — not a real content change
    config = store.get_logging_config(str(after.guild.id))
    if not config.log_message_edit:
        return
    embed = discord.Embed(
        title="Message edited",
        description=f"[Jump to message]({after.jump_url})",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Before", value=(before.content or "*(empty)*")[:1024], inline=False)
    embed.add_field(name="After", value=(after.content or "*(empty)*")[:1024], inline=False)
    embed.set_footer(text=f"{after.author} ({after.author.id}) in #{after.channel}")
    await _post(after.guild, config, embed)


async def handle_message_delete(payload: discord.RawMessageDeleteEvent, client: discord.Client) -> None:
    guild = client.get_guild(payload.guild_id) if payload.guild_id else None
    if not guild:
        return
    config = store.get_logging_config(str(guild.id))
    if not config.log_message_delete:
        return
    cached = payload.cached_message
    if cached and cached.author.bot:
        return
    channel = guild.get_channel(payload.channel_id)
    embed = discord.Embed(
        title="Message deleted",
        description=(cached.content if cached and cached.content else "*(uncached content)*")[:2000],
        color=discord.Color.red(),
    )
    footer = f"in #{channel}" if channel else f"in channel {payload.channel_id}"
    if cached:
        footer = f"{cached.author} ({cached.author.id}) {footer}"
    embed.set_footer(text=footer)
    await _post(guild, config, embed)


async def handle_member_remove(member: discord.Member) -> None:
    config = store.get_logging_config(str(member.guild.id))
    if not config.log_member_leave:
        return
    embed = discord.Embed(
        title="Member left",
        description=f"{member.mention} ({member})",
        color=discord.Color.dark_grey(),
    )
    await _post(member.guild, config, embed)


async def handle_member_ban(guild: discord.Guild, user: discord.User) -> None:
    config = store.get_logging_config(str(guild.id))
    if not config.log_member_ban:
        return
    embed = discord.Embed(
        title="Member banned",
        description=f"{user.mention} ({user})",
        color=discord.Color.red(),
    )
    await _post(guild, config, embed)


async def handle_member_unban(guild: discord.Guild, user: discord.User) -> None:
    config = store.get_logging_config(str(guild.id))
    if not config.log_member_ban:
        return
    embed = discord.Embed(
        title="Member unbanned",
        description=f"{user.mention} ({user})",
        color=discord.Color.green(),
    )
    await _post(guild, config, embed)


async def handle_member_update(before: discord.Member, after: discord.Member) -> None:
    config = store.get_logging_config(str(after.guild.id))

    if config.log_member_timeout and before.communication_disabled_until != after.communication_disabled_until:
        if after.communication_disabled_until:
            embed = discord.Embed(
                title="Member timed out",
                description=f"{after.mention} ({after}) until {after.communication_disabled_until}",
                color=discord.Color.orange(),
            )
        else:
            embed = discord.Embed(
                title="Member timeout removed",
                description=f"{after.mention} ({after})",
                color=discord.Color.green(),
            )
        await _post(after.guild, config, embed)

    if config.log_role_changes and set(before.roles) != set(after.roles):
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            parts = []
            if added:
                parts.append("Added: " + ", ".join(r.mention for r in added))
            if removed:
                parts.append("Removed: " + ", ".join(r.mention for r in removed))
            embed = discord.Embed(
                title="Member roles changed",
                description=f"{after.mention} ({after})\n" + "\n".join(parts),
                color=discord.Color.blurple(),
            )
            await _post(after.guild, config, embed)


async def handle_guild_channel_create(channel: discord.abc.GuildChannel) -> None:
    config = store.get_logging_config(str(channel.guild.id))
    if not config.log_channel_changes:
        return
    embed = discord.Embed(
        title="Channel created", description=f"#{channel.name} ({channel.id})",
        color=discord.Color.green(),
    )
    await _post(channel.guild, config, embed)


async def handle_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
    config = store.get_logging_config(str(channel.guild.id))
    if not config.log_channel_changes:
        return
    embed = discord.Embed(
        title="Channel deleted", description=f"#{channel.name} ({channel.id})",
        color=discord.Color.red(),
    )
    await _post(channel.guild, config, embed)


async def handle_guild_role_create(role: discord.Role) -> None:
    config = store.get_logging_config(str(role.guild.id))
    if not config.log_role_changes:
        return
    embed = discord.Embed(
        title="Role created", description=f"{role.mention} ({role.id})",
        color=discord.Color.green(),
    )
    await _post(role.guild, config, embed)


async def handle_guild_role_update(before: discord.Role, after: discord.Role) -> None:
    if before.name == after.name and before.permissions == after.permissions:
        return
    config = store.get_logging_config(str(after.guild.id))
    if not config.log_role_changes:
        return
    embed = discord.Embed(
        title="Role updated", description=f"{after.mention} ({after.id})",
        color=discord.Color.blurple(),
    )
    if before.name != after.name:
        embed.add_field(name="Name", value=f"{before.name} → {after.name}", inline=False)
    await _post(after.guild, config, embed)


async def handle_guild_role_delete(role: discord.Role) -> None:
    config = store.get_logging_config(str(role.guild.id))
    if not config.log_role_changes:
        return
    embed = discord.Embed(
        title="Role deleted", description=f"{role.name} ({role.id})",
        color=discord.Color.red(),
    )
    await _post(role.guild, config, embed)
