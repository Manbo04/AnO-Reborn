"""Starboard: react with the configured emoji enough times and the bot mirrors
the message into a starboard channel, updating the star count as more come in.

Uses REST fetches (channel.fetch_message) for the source message content, so
this does NOT require the message_content intent — REST always returns full
content regardless of intents (unlike live Gateway on_message events).
"""

import logging

import discord

from discord_bot import starboard_store as store

logger = logging.getLogger("ano_discord_bot")


async def _count_stars(message: discord.Message, emoji: str) -> int:
    for reaction in message.reactions:
        if str(reaction.emoji) == emoji:
            count = 0
            async for user in reaction.users():
                if not user.bot:
                    count += 1
            return count
    return 0


def _build_embed(message: discord.Message, star_count: int, emoji: str) -> discord.Embed:
    embed = discord.Embed(
        description=message.content or "*(no text content)*",
        color=discord.Color.gold(),
        timestamp=message.created_at,
    )
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})", inline=False)
    if message.attachments:
        embed.set_image(url=message.attachments[0].url)
    embed.set_footer(text=f"{emoji} {star_count} — #{message.channel}")
    return embed


async def _handle_star_change(payload, client: discord.Client) -> None:
    guild = client.get_guild(payload.guild_id)
    if not guild:
        return
    config = store.get_starboard_config(str(guild.id))
    if not config.enabled or not config.channel_id:
        return
    if str(payload.emoji) != config.emoji:
        return
    if str(payload.channel_id) == config.channel_id:
        return  # ignore stars added inside the starboard channel itself

    source_channel = guild.get_channel(payload.channel_id)
    if not isinstance(source_channel, discord.TextChannel):
        return
    try:
        source_message = await source_channel.fetch_message(payload.message_id)
    except (discord.NotFound, discord.Forbidden):
        return

    star_count = await _count_stars(source_message, config.emoji)
    existing = store.get_starboard_post(str(guild.id), str(payload.message_id))

    if existing:
        store.update_star_count(str(guild.id), str(payload.message_id), star_count)
        starboard_channel = guild.get_channel(int(config.channel_id))
        if isinstance(starboard_channel, discord.TextChannel):
            try:
                mirrored = await starboard_channel.fetch_message(int(existing.starboard_message_id))
                await mirrored.edit(embed=_build_embed(source_message, star_count, config.emoji))
            except (discord.NotFound, discord.Forbidden):
                pass
        return

    if star_count >= config.threshold:
        starboard_channel = guild.get_channel(int(config.channel_id))
        if not isinstance(starboard_channel, discord.TextChannel):
            return
        try:
            mirrored = await starboard_channel.send(embed=_build_embed(source_message, star_count, config.emoji))
        except discord.Forbidden:
            logger.warning("Missing permission to post to starboard channel in guild %s", guild.id)
            return
        store.upsert_starboard_post(
            str(guild.id), str(payload.message_id), str(payload.channel_id), str(mirrored.id), star_count
        )


async def handle_reaction_add(payload: discord.RawReactionActionEvent, client: discord.Client) -> None:
    await _handle_star_change(payload, client)


async def handle_reaction_remove(payload: discord.RawReactionActionEvent, client: discord.Client) -> None:
    await _handle_star_change(payload, client)
