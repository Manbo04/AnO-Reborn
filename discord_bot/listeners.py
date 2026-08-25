"""Event handler logic for engagement features: XP, welcome, reaction roles."""

import logging

import discord

from discord_bot import customcommands_store, engagement_store as store
from discord_bot import moderation_listeners
from discord_bot import starboard_listeners
from discord_bot.xp import award_message_xp

logger = logging.getLogger("ano_discord_bot")


async def handle_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild:
        return
    if not isinstance(message.author, discord.Member):
        return
    try:
        await award_message_xp(message.author)
    except Exception as exc:
        logger.warning("XP award failed for %s: %s", message.author.id, exc)

    try:
        await moderation_listeners.handle_automod_message(message)
    except Exception as exc:
        logger.warning("Automod check failed for %s: %s", message.author.id, exc)

    try:
        await handle_custom_command_trigger(message)
    except Exception as exc:
        logger.warning("Custom command check failed for %s: %s", message.author.id, exc)


async def handle_custom_command_trigger(message: discord.Message) -> None:
    content = message.content or ""
    if not content.startswith("!"):
        return
    token = content.split(maxsplit=1)[0][1:].lower()
    if not token:
        return
    cmd = customcommands_store.get_custom_command(str(message.guild.id), token)
    if not cmd:
        return
    if cmd.response_type == "embed":
        color = discord.Color.blurple()
        if cmd.embed_color:
            try:
                color = discord.Color(int(cmd.embed_color.lstrip("#"), 16))
            except ValueError:
                pass
        embed = discord.Embed(
            title=cmd.embed_title or None,
            description=cmd.response_text or None,
            color=color,
        )
        await message.channel.send(embed=embed)
    else:
        await message.channel.send(cmd.response_text or "")


def _render_template(template: str, member: discord.Member) -> str:
    return template.replace("{member}", member.mention).replace("{server}", member.guild.name)


async def handle_member_join(member: discord.Member) -> None:
    guild_id = str(member.guild.id)
    cfg = store.get_welcome_config(guild_id)

    for role_id in cfg.auto_role_ids:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role, reason="Auto-role on join")
            except discord.Forbidden:
                logger.warning("Missing permission to grant auto-role in guild %s", guild_id)
            except Exception as exc:
                logger.warning("Auto-role grant failed: %s", exc)

    if cfg.enabled and cfg.channel_id and cfg.message_template:
        channel = member.guild.get_channel(int(cfg.channel_id))
        if channel:
            try:
                await channel.send(_render_template(cfg.message_template, member))
            except discord.Forbidden:
                logger.warning("Missing permission to post welcome message in guild %s", guild_id)

    if cfg.dm_enabled and cfg.dm_template:
        try:
            await member.send(_render_template(cfg.dm_template, member))
        except discord.Forbidden:
            pass  # user has DMs closed — not an error worth logging


async def handle_reaction_add(payload: discord.RawReactionActionEvent, client: discord.Client) -> None:
    try:
        await starboard_listeners.handle_reaction_add(payload, client)
    except Exception as exc:
        logger.warning("Starboard check failed for message %s: %s", payload.message_id, exc)

    if payload.member is None or payload.member.bot:
        return
    role_id = store.get_reaction_role(str(payload.guild_id), str(payload.message_id), str(payload.emoji))
    if not role_id:
        return
    guild = client.get_guild(payload.guild_id)
    if not guild:
        return
    role = guild.get_role(int(role_id))
    if role:
        try:
            await payload.member.add_roles(role, reason="Reaction role")
        except discord.Forbidden:
            logger.warning("Missing permission to grant reaction role in guild %s", payload.guild_id)


async def handle_reaction_remove(payload: discord.RawReactionActionEvent, client: discord.Client) -> None:
    try:
        await starboard_listeners.handle_reaction_remove(payload, client)
    except Exception as exc:
        logger.warning("Starboard check failed for message %s: %s", payload.message_id, exc)

    role_id = store.get_reaction_role(str(payload.guild_id), str(payload.message_id), str(payload.emoji))
    if not role_id:
        return
    guild = client.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    role = guild.get_role(int(role_id))
    if member and role:
        try:
            await member.remove_roles(role, reason="Reaction role removed")
        except discord.Forbidden:
            logger.warning("Missing permission to remove reaction role in guild %s", payload.guild_id)
