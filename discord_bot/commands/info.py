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
            from discord_bot.config import GAME_BASE_URL
            from discord_bot.embeds import ANO_CRIMSON

            nation_id = data.get("nation_id")
            embed = discord.Embed(
                title=f"⚔️ Active wars · Nation #{nation_id}",
                description=f"[Open nation]({GAME_BASE_URL}/country/id={nation_id})",
                color=ANO_CRIMSON,
            )
            for w in wars[:12]:
                opp_id = w.get("opponent_id")
                opp_name = w.get("opponent_name", "?")
                opp_link = (
                    f"[{opp_name}]({GAME_BASE_URL}/country/id={opp_id})"
                    if opp_id
                    else f"**{opp_name}**"
                )
                embed.add_field(
                    name=f"War #{w['war_id']}",
                    value=f"vs {opp_link}\n**Side:** {w.get('side', '?')}",
                    inline=True,
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
