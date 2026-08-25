"""Moderation slash commands: warn/kick/ban/timeout, auto-mod config, case log."""

from datetime import timedelta

import discord
from discord import app_commands

from discord_bot import moderation_store as store
from discord_bot.permissions import require_guild_admin, require_guild_staff


def register_commands(tree: app_commands.CommandTree, backend) -> None:
    @tree.command(name="warn", description="Warn a member (logged as a case, no other action)")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    @require_guild_staff()
    async def warn(interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        await interaction.response.defer(ephemeral=True)
        case_id = store.create_case(
            str(interaction.guild.id), "warn", str(member.id), str(interaction.user.id), reason
        )
        try:
            await member.send(f"You were warned in **{interaction.guild.name}**: {reason}")
        except discord.Forbidden:
            pass
        await interaction.followup.send(f"Case #{case_id}: warned {member.mention}. {reason}", ephemeral=True)

    @tree.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason for the kick")
    @require_guild_staff()
    async def kick(interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await interaction.followup.send("Missing permission to kick that member.", ephemeral=True)
            return
        case_id = store.create_case(
            str(interaction.guild.id), "kick", str(member.id), str(interaction.user.id), reason
        )
        await interaction.followup.send(f"Case #{case_id}: kicked {member.mention}. {reason}", ephemeral=True)

    @tree.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="Member to ban",
        reason="Reason for the ban",
        delete_message_days="Delete this many days of their recent messages (0-7)",
    )
    @require_guild_staff()
    async def ban(
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        delete_message_days: int = 0,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await member.ban(
                reason=reason,
                delete_message_seconds=max(0, min(delete_message_days, 7)) * 86400,
            )
        except discord.Forbidden:
            await interaction.followup.send("Missing permission to ban that member.", ephemeral=True)
            return
        case_id = store.create_case(
            str(interaction.guild.id), "ban", str(member.id), str(interaction.user.id), reason
        )
        await interaction.followup.send(f"Case #{case_id}: banned {member.mention}. {reason}", ephemeral=True)

    @tree.command(name="unban", description="Unban a user by their Discord user ID")
    @app_commands.describe(user_id="Numeric Discord user ID to unban", reason="Reason for the unban")
    @require_guild_staff()
    async def unban(interaction: discord.Interaction, user_id: str, reason: str = "") -> None:
        await interaction.response.defer(ephemeral=True)
        if not user_id.isdigit():
            await interaction.followup.send("That doesn't look like a numeric user ID.", ephemeral=True)
            return
        try:
            await interaction.guild.unban(discord.Object(int(user_id)), reason=reason or None)
        except discord.NotFound:
            await interaction.followup.send("That user isn't banned.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.followup.send("Missing permission to unban.", ephemeral=True)
            return
        case_id = store.create_case(
            str(interaction.guild.id), "unban", user_id, str(interaction.user.id), reason
        )
        await interaction.followup.send(f"Case #{case_id}: unbanned user {user_id}.", ephemeral=True)

    @tree.command(name="timeout", description="Time out a member for a number of minutes")
    @app_commands.describe(member="Member to time out", minutes="Duration in minutes", reason="Reason")
    @require_guild_staff()
    async def timeout(
        interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await member.timeout(timedelta(minutes=minutes), reason=reason)
        except discord.Forbidden:
            await interaction.followup.send("Missing permission to time out that member.", ephemeral=True)
            return
        case_id = store.create_case(
            str(interaction.guild.id), "timeout", str(member.id), str(interaction.user.id), reason, minutes
        )
        await interaction.followup.send(
            f"Case #{case_id}: timed out {member.mention} for {minutes}m. {reason}", ephemeral=True
        )

    @tree.command(name="untimeout", description="Remove an active timeout from a member")
    @app_commands.describe(member="Member to remove the timeout from")
    @require_guild_staff()
    async def untimeout(interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await member.timeout(None)
        except discord.Forbidden:
            await interaction.followup.send("Missing permission to update that member.", ephemeral=True)
            return
        store.create_case(
            str(interaction.guild.id), "untimeout", str(member.id), str(interaction.user.id)
        )
        await interaction.followup.send(f"Removed timeout from {member.mention}.", ephemeral=True)

    @tree.command(name="clear", description="Bulk-delete recent messages in this channel")
    @app_commands.describe(
        amount="How many recent messages to delete (max 100)",
        member="Only delete messages from this member",
    )
    @require_guild_staff()
    async def clear(
        interaction: discord.Interaction, amount: int, member: discord.Member = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        amount = max(1, min(amount, 100))
        check = (lambda m: m.author.id == member.id) if member else None
        try:
            deleted = await interaction.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            await interaction.followup.send("Missing permission to manage messages here.", ephemeral=True)
            return
        await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)

    @tree.command(name="cases", description="Show recent moderation cases for a member")
    @app_commands.describe(member="Member to look up")
    @require_guild_staff()
    async def cases(interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        rows = store.list_cases(str(interaction.guild.id), target_user_id=str(member.id))
        if not rows:
            await interaction.followup.send(f"No cases found for {member.mention}.", ephemeral=True)
            return
        lines = [
            f"**#{c.id}** {c.action} — {c.reason or 'no reason given'} "
            f"({c.created_at:%Y-%m-%d %H:%M})"
            for c in rows
        ]
        embed = discord.Embed(
            title=f"Cases for {member.display_name}",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---- Auto-mod configuration (admin tier — policy, not a single action) ----

    automod_group = app_commands.Group(
        name="automod",
        description="Configure auto-mod filters",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @automod_group.command(name="config", description="Configure auto-mod filters and log channel")
    @app_commands.describe(
        log_channel="Channel to post auto-mod and moderation-case embeds to",
        spam="Enable spam/rate-limit filter",
        invites="Enable invite-link filter",
        mass_mentions="Enable mass-mention filter",
        bad_words="Enable bad-word filter",
        action="What to do when a filter triggers",
        timeout_minutes="Timeout duration when action is delete_timeout",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Delete + warn", value="delete_warn"),
            app_commands.Choice(name="Delete + timeout", value="delete_timeout"),
            app_commands.Choice(name="Delete only", value="delete_only"),
        ]
    )
    @require_guild_admin()
    async def automod_config(
        interaction: discord.Interaction,
        log_channel: discord.TextChannel = None,
        spam: bool = None,
        invites: bool = None,
        mass_mentions: bool = None,
        bad_words: bool = None,
        action: app_commands.Choice[str] = None,
        timeout_minutes: int = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        config = store.get_moderation_config(str(interaction.guild.id))
        if log_channel is not None:
            config.log_channel_id = str(log_channel.id)
        if spam is not None:
            config.filter_spam_enabled = spam
        if invites is not None:
            config.filter_invites_enabled = invites
        if mass_mentions is not None:
            config.filter_mass_mentions_enabled = mass_mentions
        if bad_words is not None:
            config.filter_bad_words_enabled = bad_words
        if action is not None:
            config.filter_action = action.value
        if timeout_minutes is not None:
            config.filter_timeout_minutes = timeout_minutes
        store.set_moderation_config(config)
        await interaction.followup.send("Auto-mod config updated.", ephemeral=True)

    badword_group = app_commands.Group(
        name="badword",
        description="Manage the auto-mod bad-word list",
        parent=automod_group,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @badword_group.command(name="add", description="Add a word to the bad-word filter")
    @require_guild_admin()
    async def badword_add(interaction: discord.Interaction, word: str) -> None:
        await interaction.response.defer(ephemeral=True)
        store.add_bad_word(str(interaction.guild.id), word)
        await interaction.followup.send(f"Added `{word.strip().lower()}` to the bad-word list.", ephemeral=True)

    @badword_group.command(name="remove", description="Remove a word from the bad-word filter")
    @require_guild_admin()
    async def badword_remove(interaction: discord.Interaction, word: str) -> None:
        await interaction.response.defer(ephemeral=True)
        store.remove_bad_word(str(interaction.guild.id), word.strip().lower())
        await interaction.followup.send(f"Removed `{word.strip().lower()}` from the bad-word list.", ephemeral=True)

    tree.add_command(automod_group)
