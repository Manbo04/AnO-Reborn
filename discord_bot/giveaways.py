"""Giveaway winner resolution — shared by the periodic loop and /giveaway end."""

import logging
import random

import discord

from discord_bot import engagement_store as store

logger = logging.getLogger("ano_discord_bot")


async def _draw_and_announce(client: discord.Client, giveaway: store.Giveaway) -> None:
    channel = client.get_channel(int(giveaway.channel_id))
    if not channel or not giveaway.message_id:
        store.mark_giveaway_ended(giveaway.id)
        return
    try:
        msg = await channel.fetch_message(int(giveaway.message_id))
    except (discord.NotFound, discord.Forbidden):
        store.mark_giveaway_ended(giveaway.id)
        return

    entrants = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    entrants.append(user)
            break

    store.mark_giveaway_ended(giveaway.id)

    if not entrants:
        await channel.send(f"🎉 Giveaway for **{giveaway.prize}** ended — nobody entered.")
        return

    winners = random.sample(entrants, k=min(giveaway.winners_count, len(entrants)))
    mentions = ", ".join(w.mention for w in winners)
    await channel.send(f"🎉 Congratulations {mentions}! You won **{giveaway.prize}**!")


async def resolve_due_giveaways(client: discord.Client) -> None:
    for giveaway in store.get_due_giveaways():
        try:
            await _draw_and_announce(client, giveaway)
        except Exception as exc:
            logger.warning("Giveaway resolution failed (id=%s): %s", giveaway.id, exc)
            store.mark_giveaway_ended(giveaway.id)


async def resolve_giveaway_by_message(client: discord.Client, guild_id: str, message_id: str) -> bool:
    for giveaway in store.list_active_giveaways(guild_id):
        if giveaway.message_id == message_id:
            await _draw_and_announce(client, giveaway)
            return True
    return False
