"""Read-only slash command for custom commands/tags — CRUD lives on the dashboard."""

import discord
from discord import app_commands

from discord_bot import customcommands_store as store


def register_commands(tree: app_commands.CommandTree, backend) -> None:
    tag_group = app_commands.Group(name="tag", description="Custom server commands")

    @tag_group.command(name="list", description="List this server's custom commands")
    async def tag_list(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        commands_ = store.list_custom_commands(str(interaction.guild.id))
        if not commands_:
            await interaction.followup.send(
                "No custom commands configured yet — add some on the dashboard's "
                "Custom Commands page.",
                ephemeral=True,
            )
            return
        lines = ", ".join(f"`!{c.trigger}`" for c in commands_)
        await interaction.followup.send(f"Custom commands: {lines}", ephemeral=True)

    tree.add_command(tag_group)
