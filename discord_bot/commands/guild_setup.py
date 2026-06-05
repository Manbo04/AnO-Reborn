"""Staff-only guild panel configuration (administrators only)."""


import discord
from discord import app_commands

from discord_bot.guild_store import (
    PANEL_KEYS,
    bind_panel_channel,
    ensure_guild_row,
    get_guild_settings,
    set_admin_role,
    set_panels_enabled,
)
from discord_bot.panel_service import refresh_guild_panels
from discord_bot.permissions import require_guild_admin

PANEL_CHOICES = [
    app_commands.Choice(name="readme — bot guide", value="readme"),
    app_commands.Choice(name="leaderboard — influence board", value="leaderboard"),
    app_commands.Choice(name="war_feed — active wars", value="war_feed"),
    app_commands.Choice(name="inspector — realm stats", value="inspector"),
    app_commands.Choice(name="world_status — global affairs", value="world_status"),
    app_commands.Choice(name="alerts — announcements", value="alerts"),
]

STAFF_CHANNEL_BLUEPRINT = """
**Suggested AnO channel layout** (create under a category e.g. `Affairs & Order`):

| Channel | Purpose |
|---------|---------|
| `#📜-bot-guide` | readme panel |
| `#🏆-influence-board` | leaderboard |
| `#⚔️-war-feed` | war feed |
| `#🔬-nation-inspector` | inspector |
| `#🌍-global-affairs` | world status |
| `#📢-realm-alerts` | public alerts |
| `#🛡️-staff-commands` | staff only — hide from @everyone |

Then bind each with `/guild_bind_panel` in that channel.
Lock `#🛡️-staff-commands` so only your staff role can view it.
"""


def register_commands(tree: app_commands.CommandTree) -> None:
    guild_group = app_commands.Group(
        name="guild",
        description="Configure Discord server panels (administrators only)",
        default_permissions=discord.Permissions(administrator=True),
    )

    @guild_group.command(
        name="bind_panel",
        description="Bind this panel type to the current channel (or a chosen channel)",
    )
    @app_commands.describe(
        panel="Which panel to post here",
        channel="Channel (defaults to where you run the command)",
    )
    @app_commands.choices(panel=PANEL_CHOICES)
    @require_guild_admin()
    async def bind_panel(
        interaction: discord.Interaction,
        panel: app_commands.Choice[str],
        channel: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("This command only works in a server.")
            return
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.followup.send("Choose a text channel.")
            return
        bind_panel_channel(str(interaction.guild.id), panel.value, str(target.id))
        bot = interaction.client
        count = await refresh_guild_panels(bot, interaction.guild.id)
        await interaction.followup.send(
            f"Bound **{panel.name}** → {target.mention}. Refreshed {count} panel(s).",
            ephemeral=True,
        )

    @guild_group.command(
        name="refresh_panels",
        description="Update all bound panel embeds with live game data",
    )
    @require_guild_admin()
    async def refresh_panels(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return
        ensure_guild_row(str(interaction.guild.id))
        set_panels_enabled(str(interaction.guild.id), True)
        count = await refresh_guild_panels(interaction.client, interaction.guild.id)
        await interaction.followup.send(
            f"Refreshed **{count}** panel message(s).", ephemeral=True
        )

    @guild_group.command(
        name="set_admin_role",
        description="Discord role that may use staff commands (in addition to Admins)",
    )
    @require_guild_admin()
    async def set_admin_role_cmd(
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        if not interaction.guild:
            return
        set_admin_role(str(interaction.guild.id), str(role.id))
        await interaction.response.send_message(
            f"Staff role set to {role.mention}. Members with this role or "
            "**Administrator** may use `/guild_*` and `/admin_*`.",
            ephemeral=True,
        )

    @guild_group.command(
        name="panel_status",
        description="Show which panels are configured for this server",
    )
    @require_guild_admin()
    async def panel_status(interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        settings = get_guild_settings(str(interaction.guild.id))
        if not settings or not settings.panel_channels:
            await interaction.response.send_message(
                "No panels bound yet. See `/guild_setup_guide`.",
                ephemeral=True,
            )
            return
        lines = [
            f"• **{key}** → <#{cid}>"
            for key in PANEL_KEYS
            if (cid := settings.panel_channels.get(key))
        ]
        await interaction.response.send_message(
            "\n".join(lines) or "No panels bound.",
            ephemeral=True,
        )

    @guild_group.command(
        name="setup_guide",
        description="Channel layout and setup steps for server staff",
    )
    @require_guild_admin()
    async def setup_guide(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(STAFF_CHANNEL_BLUEPRINT, ephemeral=True)

    tree.add_command(guild_group)
