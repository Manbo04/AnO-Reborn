import logging

import discord
from discord import app_commands

from discord_bot.backend import BotBackend, BotBackendError
from discord_bot.embeds import build_nation_embed

logger = logging.getLogger(__name__)


def register_commands(
    tree: app_commands.CommandTree, backend: BotBackend
) -> None:
    @tree.command(
        name="me",
        description="Show your linked nation — economy, military, resources, wars",
    )
    async def me_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            data = backend.me(str(interaction.user.id))
            embed = build_nation_embed(data, "Your nation")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception as exc:
            logger.exception("/me failed for discord user %s", interaction.user.id)
            await interaction.followup.send(
                "Could not load nation statistics. Please try again later.",
                ephemeral=True,
            )

    @tree.command(
        name="nation",
        description="Look up any nation by username or id (full stats)",
    )
    @app_commands.describe(identifier="Nation name or numeric id")
    async def nation_cmd(
        interaction: discord.Interaction, identifier: str
    ) -> None:
        await interaction.response.defer()
        try:
            data = backend.nation(identifier.strip())
            embed = build_nation_embed(data, "Nation lookup")
            await interaction.followup.send(embed=embed)
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @tree.command(
        name="wars",
        description="List active wars for you or another nation",
    )
    @app_commands.describe(
        nation="Optional nation name or id (defaults to your linked nation)"
    )
    async def wars_cmd(
        interaction: discord.Interaction, nation: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=bool(nation is None))
        try:
            if nation:
                data = backend.wars(nation=nation.strip())
            else:
                data = backend.wars(discord_user_id=str(interaction.user.id))
            wars = data.get("wars") or []
            if not wars:
                await interaction.followup.send(
                    "No active wars.",
                    ephemeral=not nation,
                )
                return
            embed = discord.Embed(
                title=f"Active wars (nation {data.get('nation_id')})",
                color=discord.Color.orange(),
            )
            for w in wars[:15]:
                embed.add_field(
                    name=f"War #{w['war_id']}",
                    value=(
                        f"**{w['opponent_name']}** (id {w['opponent_id']})\n"
                        f"You are: {w['side']}"
                    ),
                    inline=False,
                )
            await interaction.followup.send(
                embed=embed, ephemeral=not nation
            )
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @tree.command(
        name="resources",
        description="Top resources for you or another nation",
    )
    @app_commands.describe(
        nation="Optional nation name or id (defaults to your linked nation)"
    )
    async def resources_cmd(
        interaction: discord.Interaction, nation: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=bool(nation is None))
        try:
            if nation:
                data = backend.resources(nation=nation.strip())
            else:
                data = backend.resources(discord_user_id=str(interaction.user.id))
            embed = build_nation_embed(
                data,
                f"Resources — {data.get('username', '?')}",
            )
            await interaction.followup.send(
                embed=embed, ephemeral=not nation
            )
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
