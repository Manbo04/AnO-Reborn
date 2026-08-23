"""Engagement slash commands: leveling, welcome, reaction roles, polls, giveaways."""

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

from discord_bot import engagement_store as store
from discord_bot.permissions import require_guild_admin


def register_commands(tree: app_commands.CommandTree, backend) -> None:
    # ---- Leveling ----

    @tree.command(name="rank", description="Show your (or someone else's) level and XP")
    @app_commands.describe(member="Whose rank to show (defaults to you)")
    async def rank(interaction: discord.Interaction, member: discord.Member = None) -> None:
        if not interaction.guild:
            return
        target = member or interaction.user
        xp, level, _ = store.get_user_xp(str(interaction.guild.id), str(target.id))
        next_level_xp = 5 * (level + 1) ** 2 + 50 * (level + 1)
        embed = discord.Embed(
            title=f"{target.display_name}'s rank",
            description=f"Level **{level}** — {xp} XP\n{max(next_level_xp - xp, 0)} XP to next level",
            color=discord.Color.blurple(),
        )
        if isinstance(target, discord.Member):
            embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @tree.command(name="leaderboard", description="Top members by XP in this server")
    async def leaderboard(interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.defer()
        rows = store.get_leaderboard(str(interaction.guild.id), limit=10)
        if not rows:
            await interaction.followup.send("No XP recorded yet — start chatting!")
            return
        lines = []
        for i, (user_id, xp, level) in enumerate(rows, start=1):
            member = interaction.guild.get_member(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
            lines.append(f"**{i}.** {name} — Level {level} ({xp} XP)")
        embed = discord.Embed(
            title=f"🏆 {interaction.guild.name} Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.followup.send(embed=embed)

    levels_group = app_commands.Group(
        name="levels",
        description="Configure the leveling system",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @levels_group.command(name="config", description="Set XP rate, cooldown, and level-up channel")
    @app_commands.describe(
        xp_per_message="XP awarded per eligible message (default 15)",
        cooldown_seconds="Seconds between XP awards per user (default 60)",
        level_up_channel="Channel for level-up announcements",
        announce="Whether to announce level-ups",
    )
    @require_guild_admin()
    async def levels_config(
        interaction: discord.Interaction,
        xp_per_message: int = None,
        cooldown_seconds: int = None,
        level_up_channel: discord.TextChannel = None,
        announce: bool = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        config = store.get_level_config(str(interaction.guild.id))
        if xp_per_message is not None:
            config.xp_per_message = xp_per_message
        if cooldown_seconds is not None:
            config.xp_cooldown_seconds = cooldown_seconds
        if level_up_channel is not None:
            config.level_up_channel_id = str(level_up_channel.id)
        if announce is not None:
            config.level_up_enabled = announce
        store.set_level_config(config)
        await interaction.followup.send("Leveling config updated.", ephemeral=True)

    @levels_group.command(name="set_reward", description="Grant a role automatically at a given level")
    @app_commands.describe(level="Level to trigger the reward", role="Role to grant")
    @require_guild_admin()
    async def levels_set_reward(interaction: discord.Interaction, level: int, role: discord.Role) -> None:
        await interaction.response.defer(ephemeral=True)
        store.set_level_role(str(interaction.guild.id), level, str(role.id))
        await interaction.followup.send(
            f"Members reaching level {level} will now receive {role.mention}.", ephemeral=True
        )

    tree.add_command(levels_group)

    # ---- Welcome / auto-roles ----

    welcome_group = app_commands.Group(
        name="welcome",
        description="Configure welcome messages and auto-roles",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @welcome_group.command(name="config", description="Set the welcome message and channel")
    @app_commands.describe(
        channel="Channel to post welcome messages in",
        message="Welcome message. Use {member} and {server}",
        enabled="Turn welcome messages on/off",
    )
    @require_guild_admin()
    async def welcome_config(
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        message: str = None,
        enabled: bool = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        cfg = store.get_welcome_config(str(interaction.guild.id))
        if channel is not None:
            cfg.channel_id = str(channel.id)
        if message is not None:
            cfg.message_template = message
        if enabled is not None:
            cfg.enabled = enabled
        store.set_welcome_config(cfg)
        await interaction.followup.send("Welcome config updated.", ephemeral=True)

    @welcome_group.command(name="dm", description="Set a DM sent to new members")
    @app_commands.describe(message="DM message. Use {member} and {server}", enabled="Turn welcome DMs on/off")
    @require_guild_admin()
    async def welcome_dm(interaction: discord.Interaction, message: str = None, enabled: bool = None) -> None:
        await interaction.response.defer(ephemeral=True)
        cfg = store.get_welcome_config(str(interaction.guild.id))
        if message is not None:
            cfg.dm_template = message
        if enabled is not None:
            cfg.dm_enabled = enabled
        store.set_welcome_config(cfg)
        await interaction.followup.send("Welcome DM config updated.", ephemeral=True)

    @welcome_group.command(name="autorole", description="Add or remove a role granted automatically on join")
    @app_commands.describe(role="Role to toggle", action="add or remove")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ]
    )
    @require_guild_admin()
    async def welcome_autorole(
        interaction: discord.Interaction, role: discord.Role, action: app_commands.Choice[str]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        cfg = store.get_welcome_config(str(interaction.guild.id))
        role_id = str(role.id)
        if action.value == "add" and role_id not in cfg.auto_role_ids:
            cfg.auto_role_ids.append(role_id)
        elif action.value == "remove" and role_id in cfg.auto_role_ids:
            cfg.auto_role_ids.remove(role_id)
        store.set_welcome_config(cfg)
        shown = ", ".join(f"<@&{r}>" for r in cfg.auto_role_ids) or "none"
        await interaction.followup.send(f"Auto-roles: {shown}", ephemeral=True)

    tree.add_command(welcome_group)

    # ---- Reaction roles ----

    reactionrole_group = app_commands.Group(
        name="reactionrole",
        description="Manage reaction roles",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @reactionrole_group.command(name="add", description="Bind an emoji reaction on a message to a role")
    @app_commands.describe(
        message_id="ID of the message to watch", emoji="Emoji members react with", role="Role to grant"
    )
    @require_guild_admin()
    async def reactionrole_add(
        interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        store.add_reaction_role(str(interaction.guild.id), message_id, emoji, str(role.id))
        for channel in interaction.guild.text_channels:
            try:
                msg = await channel.fetch_message(int(message_id))
                await msg.add_reaction(emoji)
                break
            except (discord.NotFound, discord.Forbidden, ValueError):
                continue
        await interaction.followup.send(
            f"Reacting with {emoji} on that message now grants {role.mention}.", ephemeral=True
        )

    @reactionrole_group.command(name="remove", description="Unbind a reaction role")
    @app_commands.describe(message_id="ID of the message", emoji="Emoji to unbind")
    @require_guild_admin()
    async def reactionrole_remove(interaction: discord.Interaction, message_id: str, emoji: str) -> None:
        await interaction.response.defer(ephemeral=True)
        store.remove_reaction_role(str(interaction.guild.id), message_id, emoji)
        await interaction.followup.send("Reaction role removed.", ephemeral=True)

    tree.add_command(reactionrole_group)

    # ---- Polls ----

    @tree.command(name="poll", description="Post a quick yes/no poll")
    @app_commands.describe(question="The question to ask")
    async def poll(interaction: discord.Interaction, question: str) -> None:
        embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.blurple())
        embed.set_footer(text=f"Started by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    # ---- Giveaways ----

    giveaway_group = app_commands.Group(
        name="giveaway",
        description="Run giveaways",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @giveaway_group.command(name="start", description="Start a giveaway")
    @app_commands.describe(prize="What's being given away", minutes="Duration in minutes", winners="Number of winners")
    @require_guild_admin()
    async def giveaway_start(
        interaction: discord.Interaction, prize: str, minutes: int, winners: int = 1
    ) -> None:
        await interaction.response.defer()
        ends_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        giveaway_id = store.create_giveaway(
            str(interaction.guild.id), str(interaction.channel.id), prize, winners, ends_at
        )
        embed = discord.Embed(
            title=f"🎉 Giveaway: {prize}",
            description=(
                f"React with 🎉 to enter!\nEnds <t:{int(ends_at.timestamp())}:R>\nWinners: {winners}"
            ),
            color=discord.Color.magenta(),
        )
        await interaction.followup.send(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")
        store.set_giveaway_message(giveaway_id, str(msg.id))

    @giveaway_group.command(name="end", description="End a giveaway early and draw winners now")
    @app_commands.describe(message_id="Message ID of the giveaway to end")
    @require_guild_admin()
    async def giveaway_end(interaction: discord.Interaction, message_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        from discord_bot.giveaways import resolve_giveaway_by_message

        resolved = await resolve_giveaway_by_message(
            interaction.client, str(interaction.guild.id), message_id
        )
        if resolved:
            await interaction.followup.send("Giveaway ended and winners drawn.", ephemeral=True)
        else:
            await interaction.followup.send(
                "No active giveaway found with that message ID.", ephemeral=True
            )

    tree.add_command(giveaway_group)
