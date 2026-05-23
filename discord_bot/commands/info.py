import asyncio
import logging
import os

import discord
from discord import app_commands

from discord_bot.backend import BotBackend, BotBackendError, backend_mode_label
from discord_bot.embeds import EMBED_UI_VERSION, build_nation_embed

logger = logging.getLogger(__name__)


def _embed_from_payload(payload: dict) -> discord.Embed | None:
    if isinstance(payload.get("embed"), dict):
        return discord.Embed.from_dict(payload["embed"])
    return None


async def _send_nation_card(
    interaction: discord.Interaction,
    payload: dict,
    *,
    fallback_title: str,
    ephemeral: bool,
) -> None:
    embed = _embed_from_payload(payload)
    if embed is None:
        embed = build_nation_embed(payload, fallback_title)
    await interaction.followup.send(embed=embed, ephemeral=ephemeral)


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
            data = await asyncio.to_thread(backend.me, str(interaction.user.id))
            await _send_nation_card(
                interaction, data, fallback_title="Your nation", ephemeral=True
            )
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
            data = await asyncio.to_thread(backend.nation, identifier.strip())
            await _send_nation_card(
                interaction, data, fallback_title="Nation lookup", ephemeral=False
            )
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
                ident = nation.strip()
                data = await asyncio.to_thread(lambda: backend.wars(nation=ident))
            else:
                uid = str(interaction.user.id)
                data = await asyncio.to_thread(
                    lambda: backend.wars(discord_user_id=uid)
                )
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
                ident = nation.strip()
                data = await asyncio.to_thread(
                    lambda: backend.resources(nation=ident)
                )
            else:
                uid = str(interaction.user.id)
                data = await asyncio.to_thread(
                    lambda: backend.resources(discord_user_id=uid)
                )
            title = f"Resources — {data.get('username', '?')}"
            await _send_nation_card(
                interaction, data, fallback_title=title, ephemeral=not nation
            )
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @tree.command(
        name="bot_version",
        description="Check which bot build is running (use if embeds look outdated)",
    )
    async def bot_version_cmd(interaction: discord.Interaction) -> None:
        sha = (os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "").strip()
        sha_short = sha[:7] if sha else "unknown"
        embed = discord.Embed(
            title="🤖 Bot build info",
            description=(
                "If `/nation` still shows plain labels like **Influence (score)** "
                "instead of **💰 Treasury**, the **bot service has not deployed** the latest code."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Embed UI", value=f"**{EMBED_UI_VERSION}**", inline=True)
        embed.add_field(name="Data mode", value=backend_mode_label(), inline=True)
        embed.add_field(name="Deploy commit", value=f"`{sha_short}`", inline=True)
        embed.set_footer(text="Redeploy Railway service «bot» from Dockerfile.discord-bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)
