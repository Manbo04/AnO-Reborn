"""Ticket slash commands: /ticket open, /ticket close.

Private-thread based, not per-ticket channels+overwrites: a normal (non-private)
thread is created in the configured ticket channel and the opener is added via
thread.add_user(), which grants them visibility into just that thread even
though the parent channel is otherwise staff-only via normal Discord
permissions (set up once, manually, by a server admin).
"""

import discord
from discord import app_commands

from discord_bot import tickets_store as store
from discord_bot.permissions import is_guild_staff


def register_commands(tree: app_commands.CommandTree, backend) -> None:
    ticket_group = app_commands.Group(name="ticket", description="Open or close a support ticket")

    @ticket_group.command(name="open", description="Open a private support ticket")
    @app_commands.describe(reason="What you need help with")
    async def ticket_open(interaction: discord.Interaction, reason: str = "") -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        config = store.get_ticket_config(guild_id)
        if not config.enabled or not config.ticket_channel_id:
            await interaction.followup.send(
                "Tickets aren't set up on this server yet — ask an admin to enable "
                "them on the dashboard's Community page.",
                ephemeral=True,
            )
            return

        existing = store.get_open_ticket_for_user(guild_id, str(interaction.user.id))
        if existing:
            await interaction.followup.send(
                f"You already have an open ticket: <#{existing.thread_id}>.", ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(int(config.ticket_channel_id))
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("The configured ticket channel no longer exists.", ephemeral=True)
            return

        try:
            thread = await channel.create_thread(
                name=f"ticket-{interaction.user.name}"[:100],
                type=discord.ChannelType.private_thread,
            )
            await thread.add_user(interaction.user)
        except discord.Forbidden:
            await interaction.followup.send(
                "Missing permission to create a ticket thread — the bot needs "
                "Create Private Threads in that channel.",
                ephemeral=True,
            )
            return

        store.create_ticket(guild_id, str(interaction.user.id), str(thread.id))
        if reason:
            await thread.send(f"**{interaction.user.mention}'s ticket**\n{reason}")
        else:
            await thread.send(f"**{interaction.user.mention}'s ticket** — no reason given.")
        await interaction.followup.send(f"Ticket opened: {thread.mention}.", ephemeral=True)

    @ticket_group.command(name="close", description="Close this ticket (run inside the ticket thread)")
    async def ticket_close(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send("Run this inside the ticket thread you want to close.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        ticket = store.get_ticket_by_thread(guild_id, str(interaction.channel.id))
        if not ticket or ticket.status != "open":
            await interaction.followup.send("This thread isn't an open ticket.", ephemeral=True)
            return

        is_opener = str(interaction.user.id) == ticket.opener_user_id
        if not is_opener and not await is_guild_staff(interaction):
            await interaction.followup.send(
                "Only the ticket opener or staff can close this ticket.", ephemeral=True
            )
            return

        store.close_ticket(ticket.id, str(interaction.user.id))
        await interaction.followup.send("Ticket closed.", ephemeral=True)
        try:
            await interaction.channel.edit(archived=True, locked=True)
        except discord.Forbidden:
            pass

    tree.add_command(ticket_group)
